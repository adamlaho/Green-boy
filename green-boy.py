"""
Green-Boy: A lightweight Telegram bot for SLURM job monitoring
with enhanced resource usage monitoring capabilities and improved UI
Version 1.3.2 - Complete Enhancement with Process Protection
"""
import os
import subprocess
import logging
import sys
import asyncio
import re
import signal
import time
import json
import fcntl
import socket
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import Conflict, NetworkError

# ─── Configuration ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set")

# Optional authorized users (comma-separated list of user IDs)
AUTH_USERS_STR = os.getenv("GREENBOY_AUTH_USERS", "")
AUTHORIZED_USERS = [int(user_id.strip()) for user_id in AUTH_USERS_STR.split(",") if user_id.strip()]

# Max chars per message
MAX_MESSAGE_LENGTH = 3500

# Files and paths
CURRENT_USER = os.getenv('USER', 'unknown')
LOCK_FILE_PATH = f"/tmp/greenboy-{CURRENT_USER}.lock"  # User-specific lock file
MONITORED_JOBS_FILE = f"monitored_jobs-{CURRENT_USER}.json"  # User-specific jobs file
USER_PORT = 49152 + (hash(CURRENT_USER) % 1000)  # User-specific port between 49152-50152

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Process Lock System ────────────────────────────────────────────────────────
# Global variables for lock handling
lock_file = None
lock_socket = None

def check_running_instance():
    """
    Check if another instance is already running using both file lock and socket methods.
    Returns True if no other instance is running, False otherwise.
    """
    global lock_file, lock_socket
    
    # Method 1: File locking
    try:
        lock_file = open(LOCK_FILE_PATH, 'w')
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Write PID to the file
        lock_file.truncate(0)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        print(f"Lock file acquired at {LOCK_FILE_PATH}")
    except IOError:
        print("Another instance is already running (file lock exists)")
        try:
            if lock_file:
                lock_file.close()
        except:
            pass
        return False
    
    # Method 2: Socket binding (double protection)
    try:
        # Try to bind to a specific port
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('localhost', USER_PORT))  # User-specific port
        print(f"Socket lock acquired on port {USER_PORT}")
    except socket.error:
        print(f"Another instance is already running (port {USER_PORT} is in use)")
        try:
            if lock_file:
                lock_file.close()
        except:
            pass
        return False
        
    return True

def release_locks():
    """Release all locks when shutting down."""
    global lock_file, lock_socket
    
    print("Releasing process locks...")
    
    # Release file lock
    try:
        if lock_file:
            lock_file.close()
            print("File lock released")
    except Exception as e:
        print(f"Error releasing file lock: {e}")
    
    # Release socket lock
    try:
        if lock_socket:
            lock_socket.close()
            print("Socket lock released")
    except Exception as e:
        print(f"Error releasing socket lock: {e}")

# ─── Process Management Functions ────────────────────────────────────────────────

def kill_running_bot_processes():
    """
    Find and kill any running instances of the bot FOR THE CURRENT USER ONLY.
    Returns the number of processes killed.
    """
    import subprocess
    import signal
    import time
    
    print("Checking for running bot processes...")
    
    # Find all Python processes that match our bot's signature AND our user
    try:
        # Use different approaches to find processes
        processes = []
        current_user = os.getenv('USER', 'unknown')
        print(f"Looking for processes owned by current user: {current_user}")
        
        # Method 1: Using ps with grep (most reliable)
        try:
            ps_cmd = ["ps", "-ef"]
            ps_output = subprocess.check_output(ps_cmd, text=True)
            
            for line in ps_output.splitlines():
                # Look for green-boy.py but exclude grep processes, this process, and other users
                if "green-boy.py" in line and "grep" not in line and str(os.getpid()) not in line:
                    parts = line.split()
                    if len(parts) > 1:
                        # Check if this process belongs to the current user
                        if current_user in line:
                            pid = int(parts[1])
                            processes.append(pid)
                            print(f"Found bot process: {line.strip()}")
        except Exception as e:
            print(f"Error using ps to find processes: {e}")
        
        # Method 2: Using pgrep if available (with user filter)
        try:
            pgrep_cmd = ["pgrep", "-u", current_user, "-f", "green-boy.py"]
            pgrep_output = subprocess.check_output(pgrep_cmd, text=True)
            for line in pgrep_output.splitlines():
                try:
                    pid = int(line.strip())
                    if pid != os.getpid() and pid not in processes:  # Exclude this process
                        processes.append(pid)
                        print(f"Found bot process (pgrep): PID {pid}")
                except ValueError:
                    pass
        except (subprocess.SubprocessError, FileNotFoundError):
            # pgrep might not be available on all systems
            pass
            
        # Method 3: Check user-specific lock file for potentially stale PID
        try:
            if os.path.exists(LOCK_FILE_PATH):
                with open(LOCK_FILE_PATH, 'r') as f:
                    content = f.read().strip()
                    try:
                        pid = int(content)
                        if pid != os.getpid() and pid not in processes:
                            processes.append(pid)
                            print(f"Found bot process from lock file: PID {pid}")
                    except ValueError:
                        pass
                # Always remove the lock file to clean stale locks
                try:
                    os.remove(LOCK_FILE_PATH)
                    print(f"Removed potentially stale lock file: {LOCK_FILE_PATH}")
                except:
                    pass
        except Exception as e:
            print(f"Error checking lock file: {e}")
            
        # Try to kill processes in original and reverse order (sometimes killing
        # parent processes first helps)
        processes_to_try = list(processes) + list(reversed(processes))
        killed_count = 0
        killed_pids = set()  # Track which PIDs we've already killed
        
        for pid in processes_to_try:
            if pid in killed_pids:
                continue  # Skip if we've already killed this one
                
            try:
                # First try SIGTERM for graceful shutdown
                print(f"Attempting to terminate process {pid}...")
                os.kill(pid, signal.SIGTERM)
                
                # Wait a bit to see if it terminates
                for _ in range(5):  # Wait up to 5 seconds
                    time.sleep(1)
                    try:
                        # Check if process still exists
                        os.kill(pid, 0)
                    except OSError:
                        # Process no longer exists
                        print(f"Process {pid} terminated successfully")
                        killed_count += 1
                        killed_pids.add(pid)
                        break
                else:
                    # Process didn't terminate, use SIGKILL
                    print(f"Process {pid} didn't terminate gracefully, forcing kill...")
                    try:
                        os.kill(pid, signal.SIGKILL)
                        killed_count += 1
                        killed_pids.add(pid)
                        print(f"Process {pid} killed")
                    except Exception as e:
                        print(f"Error killing process {pid} with SIGKILL: {e}")
                    
            except OSError as e:
                if e.errno == 3:  # No such process
                    print(f"Process {pid} no longer exists")
                else:
                    print(f"Error killing process {pid}: {e}")
        
        # Also use killall as a last resort - but only for current user's processes
        try:
            # This will fail if no processes match, which is fine
            killall_cmd = ["killall", "-u", current_user, "-9", "green-boy.py"]
            subprocess.run(killall_cmd, stderr=subprocess.DEVNULL)
            print(f"Attempted killall for user {current_user}")
        except:
            pass
            
        # Check for and remove any socket binding on our user's port
        try:
            # Try to create a socket and bind it - if it fails, something is still using the port
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.bind(('localhost', USER_PORT))
            test_socket.close()
            print(f"Port {USER_PORT} is free")
        except socket.error:
            print(f"Port {USER_PORT} is still in use - attempting to free it")
            try:
                # We can only reliably free ports owned by our user
                subprocess.run(["fuser", "-k", f"{USER_PORT}/tcp"], stderr=subprocess.DEVNULL)
                print(f"Killed processes using port {USER_PORT}")
            except:
                pass
                
        # Clean up any lock file
        try:
            if os.path.exists(LOCK_FILE_PATH):
                os.remove(LOCK_FILE_PATH)
                print(f"Removed lock file {LOCK_FILE_PATH}")
        except Exception as e:
            print(f"Error removing lock file: {e}")
            
        return len(killed_pids)
        
    except Exception as e:
        print(f"Error checking for running processes: {e}")
        return 0

def aggressive_webhook_cleanup():
    """
    Aggressively clear webhook with multiple attempts and verification.
    Returns True if successful, False otherwise.
    """
    import requests
    import time
    import json
    
    print(f"Starting aggressive webhook cleanup...")
    
    # First, get the current webhook info to see if there's anything to clean
    try:
        get_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        response = requests.get(get_webhook_url, timeout=15)
        if response.status_code == 200:
            webhook_data = response.json()
            if 'result' in webhook_data:
                current_url = webhook_data['result'].get('url', '')
                if current_url:
                    print(f"Found existing webhook: {current_url}")
                else:
                    print("No webhook currently set")
    except Exception as e:
        print(f"Error checking webhook status: {e}")
    
    # Try to delete the webhook multiple times
    success = False
    for attempt in range(1, 6):  # 5 attempts
        try:
            print(f"Webhook deletion attempt {attempt}/5...")
            
            # Use both drop_pending_updates and specific HTTP headers
            delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
            headers = {
                'Connection': 'close',
                'Content-Type': 'application/json'
            }
            data = {
                'drop_pending_updates': True
            }
            
            # Use a longer timeout and explicit connection close
            response = requests.post(
                delete_url, 
                headers=headers,
                data=json.dumps(data), 
                timeout=20
            )
            
            # Check response
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('ok', False):
                    print(f"Webhook successfully deleted on attempt {attempt}")
                    
                    # Verify the webhook is truly gone
                    time.sleep(3)  # Wait before verification
                    verify_response = requests.get(get_webhook_url, timeout=15)
                    if verify_response.status_code == 200:
                        verify_data = verify_response.json()
                        if 'result' in verify_data and not verify_data['result'].get('url', ''):
                            print("Webhook deletion verified. No webhook is set now.")
                            
                            # Also clear any pending updates
                            try:
                                print("Clearing any pending updates...")
                                clear_updates_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
                                clear_data = {
                                    "offset": -1,
                                    "limit": 1,
                                    "timeout": 0,
                                    "allowed_updates": []
                                }
                                clear_response = requests.post(
                                    clear_updates_url,
                                    json=clear_data,
                                    timeout=10
                                )
                                print(f"Clear updates response: {clear_response.status_code}")
                            except Exception as e:
                                print(f"Error clearing updates: {e}")
                            
                            success = True
                            break
                        else:
                            print("Webhook still exists after deletion attempt. Will retry.")
                else:
                    print(f"Webhook deletion response not OK: {response_data}")
            else:
                print(f"Webhook deletion failed with status code: {response.status_code}")
                
        except Exception as e:
            print(f"Error in webhook deletion attempt {attempt}: {e}")
        
        # Wait longer between attempts
        wait_time = attempt * 5  # Progressive backoff
        print(f"Waiting {wait_time} seconds before next attempt...")
        time.sleep(wait_time)
    
    if success:
        # One final delay before returning to ensure everything is settled
        print("Webhook successfully cleaned up. Waiting 30 seconds for API to settle...")
        time.sleep(30)  # Increased from 10 to 30 seconds
        return True
    else:
        print("Failed to clean up webhook after multiple attempts")
        return False

# ─── Job Monitoring System ─────────────────────────────────────────────────────

# Storage for jobs being monitored (in-memory dictionary)
# Format: {job_id: {"user_id": user_id, "chat_id": chat_id, "last_state": state}}
MONITORED_JOBS = {}

def save_monitored_jobs():
    """Save monitored jobs to file"""
    try:
        with open(MONITORED_JOBS_FILE, 'w') as f:
            json.dump(MONITORED_JOBS, f)
    except Exception as e:
        logger.error(f"Error saving monitored jobs: {e}")

def load_monitored_jobs():
    """Load monitored jobs from file"""
    global MONITORED_JOBS
    try:
        with open(MONITORED_JOBS_FILE, 'r') as f:
            MONITORED_JOBS = json.load(f)
    except FileNotFoundError:
        MONITORED_JOBS = {}
    except Exception as e:
        logger.error(f"Error loading monitored jobs: {e}")
        MONITORED_JOBS = {}

# ─── Helpers ───────────────────────────────────────────────────────────────────

def is_authorized(user_id):
    """Check if a user is authorized to use the bot."""
    # If no authorized users are configured, allow all users
    if not AUTHORIZED_USERS:
        return True
    return user_id in AUTHORIZED_USERS

def run_slurm_command(cmd: list[str]) -> tuple[bool, str]:
    """Run a SLURM command and return (success, output)."""
    try:
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.debug(f"Command succeeded. Output: {result.stdout}")
        return True, result.stdout or "(command completed successfully)"
    except subprocess.CalledProcessError as e:
        logger.error(f"Command {' '.join(cmd)} failed with return code {e.returncode}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
        error = e.stderr.strip() or str(e)
        return False, f"Error: {error}"

def run_squeue(flags: list[str]) -> str:
    """Run `squeue --me [flags]` and return stdout or an error message."""
    success, output = run_slurm_command(["squeue", "--me"] + flags)
    return output if success else output or "(no jobs found)"

def get_job_details(job_id: str) -> dict:
    """Get detailed information about a job using scontrol."""
    success, output = run_slurm_command(["scontrol", "show", "job", job_id])
    if not success:
        return {"JobId": job_id, "Error": output}
    
    # Parse scontrol output into a dictionary
    details = {}
    current_line = ""
    
    # Handle multi-line output properly
    for line in output.strip().split("\n"):
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
            
        # If line starts with "JobId=", it's a new job entry
        if line.startswith("JobId="):
            current_line = line
        else:
            current_line += " " + line
            
    # Now parse the combined line
    for item in current_line.split():
        if "=" in item:
            key, value = item.split("=", 1)
            details[key] = value
    
    return details

def get_job_resource_usage(job_id: str) -> dict:
    """Get CPU and memory usage for a job."""
    # Get job state first
    job_details = get_job_details(job_id)
    job_state = job_details.get("JobState", "UNKNOWN")
    
    result = {
        "AllocatedCPUs": int(job_details.get("NumCPUs", 0)),
        "AllocatedNodes": job_details.get("NumNodes", "0"),
        "NodeList": job_details.get("NodeList", ""),
        "JobState": job_state,
        "JobId": job_details.get("JobId", job_id)
    }
    
    # For running jobs, use sstat
    if job_state == "RUNNING":
        # Basic information from sstat
        sstat_cmd = [
            "sstat", 
            f"--jobs={job_id}",  # Use equals sign format which is more reliable
            "--format=JobID,AveCPU,MaxRSS,AveRSS,MaxVMSize,AveVMSize,AveCPUFreq,ConsumedEnergy",
            "-P"  # Parsable output for easier parsing
        ]
        
        success, output = run_slurm_command(sstat_cmd)
        
        # Log the output for debugging
        logger.debug(f"sstat output for job {job_id}: {output}")
        
        if success and "No job(s) found" not in output and output.strip():
            # Parse the output
            lines = output.strip().split('\n')
            if len(lines) >= 2:  # Ensure we have header and at least one data row
                headers = lines[0].split('|')
                values = lines[1].split('|')
                
                # Create the results dictionary
                for i, header in enumerate(headers):
                    if i < len(values):
                        result[header.strip()] = values[i].strip()
        
        # Get per-task CPU usage information
        task_cmd = [
            "sstat",
            f"--jobs={job_id}",  # Use equals sign format
            "--format=JobID,AveCPU,AveRSS,MaxRSS,TaskID,CPUTime,TresUsageInTot",
            "-P"  # Parsable output
        ]
        
        success, task_output = run_slurm_command(task_cmd)
        logger.debug(f"sstat task output for job {job_id}: {task_output}")
        
        if success and "No job(s) found" not in task_output and task_output.strip():
            task_lines = task_output.strip().split('\n')
            if len(task_lines) > 1:  # Header plus at least one data row
                task_headers = task_lines[0].split('|')
                tasks = []
                for line in task_lines[1:]:
                    values = line.split('|')
                    task = {}
                    for i, header in enumerate(task_headers):
                        if i < len(values):
                            task[header.strip()] = values[i].strip()
                    tasks.append(task)
                
                result["tasks"] = tasks
    
    # For completed jobs, use sacct
    elif job_state in ["COMPLETED", "CANCELLED", "FAILED", "TIMEOUT"]:
        sacct_cmd = [
            "sacct",
            f"--jobs={job_id}",
            "--format=JobID,State,ExitCode,AveCPU,MaxRSS,AveRSS,MaxVMSize,AveVMSize,CPUTime,ConsumedEnergy,Elapsed",
            "-P"  # Parsable output
        ]
        
        success, output = run_slurm_command(sacct_cmd)
        logger.debug(f"sacct output for job {job_id}: {output}")
        
        if success and output.strip():
            # Parse the output
            lines = output.strip().split('\n')
            if len(lines) >= 2:  # Ensure we have header and at least one data row
                headers = lines[0].split('|')
                values = lines[1].split('|')
                
                # Create the results dictionary
                for i, header in enumerate(headers):
                    if i < len(values):
                        result[header.strip()] = values[i].strip()
                
                result["JobState"] = "COMPLETED"  # Ensure consistent state naming
    
    return result

def get_job_processes(job_id: str) -> str:
    """Get detailed CPU and memory usage for all processes in a job."""
    # First, get job details to check if it's running
    job_details = get_job_details(job_id)
    job_state = job_details.get("JobState", "UNKNOWN")
    nodelist = job_details.get("NodeList", "")
    
    if job_state != "RUNNING":
        return f"Job {job_id} is not running (current state: {job_state}). CPU and memory details are only available for running jobs."
    
    # Try different methods to get process information, starting with the most reliable
    
    # Method 1: Use sstat with detailed metrics
    sstat_cmd = [
        "sstat",
        f"--jobs={job_id}",
        "--format=JobID,Node,AveCPU,MinCPU,TotalCPU,AveRSS,MaxRSS,AveVMSize,MaxVMSize",
        "-P"
    ]
    
    success, sstat_output = run_slurm_command(sstat_cmd)
    
    if success and "No job(s) found" not in sstat_output and sstat_output.strip():
        # Create a table-like formatting for the output
        lines = sstat_output.strip().split('\n')
        if len(lines) >= 2:  # We have a header plus data rows
            # The first line is the header
            header = lines[0]
            # Format into a table
            result = "SLURM Resource Usage Statistics:\n\n"
            result += "\n".join(lines)
            return result
    
    # Method 2: Try to get more detailed job step info
    step_cmd = [
        "sstat",
        f"--jobs={job_id}",
        "--format=JobID,StepID,Node,Task,AveCPU,MaxRSS,AveRSS,MaxVMSize",
        "-P"
    ]
    
    success, step_output = run_slurm_command(step_cmd)
    
    if success and "No job(s) found" not in step_output and step_output.strip():
        lines = step_output.strip().split('\n')
        if len(lines) >= 2:
            # Format into a table
            result = "SLURM Job Step Statistics:\n\n"
            result += "\n".join(lines)
            return result
    
    # Method 3: Use scontrol to get process information
    scontrol_cmd = ["scontrol", "show", "-d", "job", job_id]
    success, scontrol_output = run_slurm_command(scontrol_cmd)
    
    if success and scontrol_output.strip():
        # Parse SLURM's output to extract useful info
        result = "SLURM Job Control Information:\n\n"
        
        # Extract CPU and memory-related lines
        for line in scontrol_output.split('\n'):
            # Look for CPU and memory stats
            if any(keyword in line for keyword in ["CPU", "Memory", "Mem", "Nodes", "Task", "%"]):
                result += line.strip() + "\n"
        
        if len(result.split('\n')) > 2:  # If we found some useful information
            return result
    
    # Method 4: Try squeue with detailed format
    squeue_cmd = ["squeue", "-j", job_id, "--format=%i %u %P %j %t %M %l %D %S %C %m %b %N %L %T"]
    success, squeue_output = run_slurm_command(squeue_cmd)
    
    if success and "JOBID" in squeue_output and squeue_output.strip():
        result = "SLURM Queue Information:\n\n"
        result += squeue_output.strip()
        return result
    
    # Method 5: If SSH access is available and you have credentials, try to run top remotely
    # This is commented out because it requires SSH setup and is often restricted
    # You could enable this if your environment allows it
    """
    if nodelist:
        try:
            # This requires SSH keys to be set up for password-less login
            ssh_cmd = ["ssh", nodelist.split(',')[0], "top -b -n 1 | grep -E '^[[:space:]]*[0-9]+'"]
            ssh_result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=5)
            if ssh_result.returncode == 0 and ssh_result.stdout:
                result = f"Process information from node {nodelist.split(',')[0]}:\n\n"
                result += ssh_result.stdout
                return result
        except (subprocess.SubprocessError, Exception) as e:
            logger.error(f"Error running SSH command: {e}")
    """
    
    # Method 6: As a fallback, try to get formatted sstat output that might be useful
    try:
        # Try with custom formatting to get as much information as possible
        custom_cmd = [
            "sstat",
            f"--jobs={job_id}",
            "--format=JobID,MaxVMSize,MaxVMSizeNode,MaxVMSizeTask,AveCPU,ConsumedEnergy,MaxDiskRead,MaxDiskWrite,MaxRSS,MaxRSSNode,MaxRSSTask",
            "-P"
        ]
        
        success, custom_output = run_slurm_command(custom_cmd)
        
        if success and custom_output.strip():
            result = "Resource Usage Summary:\n\n"
            
            # Try to create a nicely formatted table from the pipe-delimited output
            lines = custom_output.strip().split('\n')
            if len(lines) >= 2:
                headers = lines[0].split('|')
                values = lines[1].split('|')
                
                # Create a table-like output
                max_width = max(len(h) for h in headers) + 2
                result += "\n".join(f"{headers[i]:<{max_width}} {values[i]}" for i in range(min(len(headers), len(values))))
                
                return result
    except Exception as e:
        logger.error(f"Error in fallback sstat: {e}")
    
    # If all else fails
    return f"Process information not available. Job is running on nodes: {nodelist}\n\nDetailed CPU and memory information cannot be accessed directly from the login node."

def get_cluster_status() -> str:
    """Get overall cluster status."""
    success, output = run_slurm_command(["sinfo", "-o", "%20P %5a %14F %8z %10T %N"])
    if not success:
        return "Error retrieving cluster status."
    return output

def cleanup_on_exit():
    """Clean up when the bot is shutting down."""
    print("Bot shutting down...")
    
    # Release process locks
    release_locks()
    
    # Clear webhook
    try:
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            json={"drop_pending_updates": True},
            timeout=10
        )
        print(f"Webhook cleared on exit: {response.status_code}")
    except Exception as e:
        print(f"Could not clear webhook on exit: {e}")
        
    # Try to remove lock file if it exists
    try:
        if os.path.exists(LOCK_FILE_PATH):
            os.remove(LOCK_FILE_PATH)
            print(f"Removed lock file {LOCK_FILE_PATH}")
    except Exception as e:
        print(f"Error removing lock file: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print(f"\nReceived signal {signum}, shutting down gracefully...")
    cleanup_on_exit()
    sys.exit(0)

def paginate_lines(text: str, max_chars: int):
    """
    Yield chunks of `text` (by lines) each under max_chars.
    """
    lines = text.splitlines()
    chunk = []
    size = 0
    for line in lines:
        # +1 for the newline
        if size + len(line) + 1 > max_chars and chunk:
            yield "\n".join(chunk)
            chunk = [line]
            size = len(line) + 1
        else:
            chunk.append(line)
            size += len(line) + 1
    if chunk:
        yield "\n".join(chunk)

# ─── Enhanced Display Functions ───────────────────────────────────────────────────

def parse_squeue_output(raw_output: str) -> list[dict]:
    """Parse raw squeue output into a list of job dictionaries."""
    lines = raw_output.strip().split('\n')
    if len(lines) < 2:  # No jobs or header only
        return []
    
    # Parse header to get column names
    header = lines[0]
    # Split by whitespace but preserve multi-word fields
    header_parts = header.split()
    
    jobs = []
    # Process each job line
    for line in lines[1:]:
        # Skip empty lines
        if not line.strip():
            continue
            
        # Parse job data based on the format of squeue output
        # This requires careful handling since fields might have spaces
        job_data = {}
        
        # Split the line into parts (but be careful about fields with spaces)
        parts = line.split()
        
        # Handle standard fields
        if len(parts) >= 8:  # Minimum expected columns
            job_data['JOBID'] = parts[0]
            job_data['PARTITION'] = parts[1]
            job_data['NAME'] = parts[2]
            job_data['USER'] = parts[3]
            job_data['STATE'] = parts[4]
            job_data['TIME'] = parts[5]
            job_data['NODES'] = parts[6]
            
            # The last part might be NODELIST or REASON in parentheses
            # Combine all remaining parts for NODELIST/REASON
            job_data['NODELIST_REASON'] = ' '.join(parts[7:])
        
        jobs.append(job_data)
    
    return jobs

def get_state_emoji(state: str) -> str:
    """Return an emoji representing the job state."""
    state = state.upper()
    if state == 'R':
        return '🟢'  # Running
    elif state == 'PD':
        return '🟡'  # Pending
    elif state == 'CG':
        return '🔵'  # Completing
    elif state in ['F', 'FAILED']:
        return '🔴'  # Failed
    elif state in ['CA', 'CANCELLED']:
        return '⚫'  # Cancelled
    elif state in ['CD', 'COMPLETED']:
        return '✅'  # Completed
    elif state in ['TO', 'TIMEOUT']:
        return '⏱️'  # Timeout
    else:
        return '❓'  # Unknown state

def format_fancy_job_list(jobs: list[dict], add_buttons: bool = False) -> tuple[str, list]:
    """
    Format the jobs into a pretty display format.
    Returns formatted output and list of job IDs for buttons.
    """
    if not jobs:
        return "*No jobs found*", []
    
    # Create a formatted output with emojis and better spacing
    output = "*Your SLURM Jobs*\n\n"
    job_ids = []
    
    for job in jobs:
        # Get state with emoji
        state = job.get('STATE', '?')
        state_emoji = get_state_emoji(state)
        
        # Format job info with emojis and better layout
        job_id = job.get('JOBID', '?')
        job_ids.append(job_id)
        job_name = job.get('NAME', '?')
        partition = job.get('PARTITION', '?')
        runtime = job.get('TIME', '?')
        nodes = job.get('NODES', '?')
        
        # Get reason or nodelist
        nodelist_reason = job.get('NODELIST_REASON', '')
        reason = ""
        if '(' in nodelist_reason and ')' in nodelist_reason:
            # Extract reason in parentheses
            reason = nodelist_reason[nodelist_reason.find('(')+1:nodelist_reason.find(')')]
            if reason:
                reason = f"({reason})"
        
        # Format the job entry
        if add_buttons:
            # Make job ID plain text (buttons will be added separately)
            output += f"{state_emoji} *Job {job_id}*: `{job_name}`\n"
        else:
            # Make job ID a clickable reference
            output += f"{state_emoji} *Job {job_id}*: `{job_name}`\n"
            
        output += f"    • Partition: `{partition}`\n"
        output += f"    • Runtime: `{runtime}`\n"
        output += f"    • Nodes: `{nodes}`\n"
        
        if reason:
            output += f"    • Reason: `{reason}`\n"
            
        output += "\n"  # Add space between jobs
    
    return output, job_ids

def format_cluster_status(raw_output: str) -> str:
    """Format cluster status in a more user-friendly way."""
    lines = raw_output.strip().split('\n')
    if len(lines) < 2:
        return "*No cluster information available*"
    
    # Parse header
    header = lines[0]
    header_parts = header.split()
    
    # Create a formatted output
    output = "🖥️ *Cluster Status*\n\n"
    
    # Process each partition line
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:  # Ensure we have enough parts
            continue
        
        partition = parts[0].strip()
        avail = parts[1].strip()
        nodes = parts[2].strip()
        cpus = parts[3].strip()
        state = parts[4].strip()
        nodelist = ' '.join(parts[5:]).strip()
        
        # Determine state emoji
        state_emoji = "🔄"  # Default: mixed/partial
        if state.lower() == "idle":
            state_emoji = "🟢"  # Idle: available
        elif state.lower() == "down" or state.lower() == "drain":
            state_emoji = "🔴"  # Down/drain: unavailable
        elif state.lower() == "alloc":
            state_emoji = "🟡"  # Allocated: busy
        elif state.lower() == "mix":
            state_emoji = "🔄"  # Mix: partially busy
            
        # Format partition info
        output += f"{state_emoji} *Partition {partition}*\n"
        output += f"    • Availability: `{avail}`\n"
        output += f"    • Nodes: `{nodes}`\n" 
        output += f"    • State: `{state}`\n"
        
        # Only add nodelist if it's not too long
        if len(nodelist) < 50:
            output += f"    • Nodes: `{nodelist}`\n"
        else:
            output += f"    • Nodes: `{nodelist[:47]}...`\n"
            
        output += "\n"
    
    return output

# ─── Job Monitoring Functions ─────────────────────────────────────────────────

async def monitor_job(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: str):
    """Add a job to the monitoring list"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Clean job ID to extract just the numeric part
    clean_jobid = re.match(r'(\d+)', job_id)
    if clean_jobid:
        job_id = clean_jobid.group(1)
    
    # Check if job exists and get current state
    job_details = get_job_details(job_id)
    if "Error" in job_details:
        if update.callback_query:
            await update.callback_query.edit_message_text(f"❌ Cannot monitor job {job_id}: {job_details['Error']}")
        else:
            await update.message.reply_text(f"❌ Cannot monitor job {job_id}: {job_details['Error']}")
        return False
    
    current_state = job_details.get("JobState", "UNKNOWN")
    
    # Only monitor jobs that haven't completed yet
    if current_state in ["COMPLETED", "CANCELLED", "FAILED", "TIMEOUT"]:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                f"⚠️ Job {job_id} has already finished (state: {current_state}). Cannot monitor."
            )
        else:
            await update.message.reply_text(
                f"⚠️ Job {job_id} has already finished (state: {current_state}). Cannot monitor."
            )
        return False
    
    # Add job to monitored list
    MONITORED_JOBS[job_id] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "last_state": current_state,
        "added_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Save to file
    save_monitored_jobs()
    
    # Use callback query if available, otherwise use message
    if update.callback_query:
        await update.callback_query.answer(f"✅ Now monitoring job {job_id}")
        # Create keyboard with job info button
        keyboard = [[InlineKeyboardButton("📋 Job Details", callback_data=f"jobinfo_{job_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            f"✅ Now monitoring job {job_id}. You'll be notified when it completes.\n"
            f"Current state: {current_state}",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"✅ Now monitoring job {job_id}. You'll be notified when it completes.\n"
            f"Current state: {current_state}"
        )
    return True

async def stop_monitoring_job(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: str):
    """Remove a job from the monitoring list"""
    user_id = update.effective_user.id
    
    # Clean job ID to extract just the numeric part
    clean_jobid = re.match(r'(\d+)', job_id)
    if clean_jobid:
        job_id = clean_jobid.group(1)
    
    # Check if job is being monitored and user is authorized
    if job_id not in MONITORED_JOBS:
        # Use callback query if available, otherwise use message
        if update.callback_query:
            await update.callback_query.answer(f"❌ Job {job_id} is not being monitored.")
            await update.callback_query.edit_message_text(f"❌ Job {job_id} is not being monitored.")
        else:
            await update.message.reply_text(f"❌ Job {job_id} is not being monitored.")
        return False
    
    if MONITORED_JOBS[job_id]["user_id"] != user_id and not is_authorized(user_id):
        # Use callback query if available, otherwise use message
        if update.callback_query:
            await update.callback_query.answer(f"⛔ Not authorized")
            await update.callback_query.edit_message_text(f"⛔ You are not authorized to stop monitoring job {job_id}.")
        else:
            await update.message.reply_text(f"⛔ You are not authorized to stop monitoring job {job_id}.")
        return False
    
    # Remove job from monitored list
    del MONITORED_JOBS[job_id]
    
    # Save to file
    save_monitored_jobs()
    
    # Use callback query if available, otherwise use message
    if update.callback_query:
        await update.callback_query.answer(f"✅ Stopped monitoring job {job_id}")
        await update.callback_query.edit_message_text(f"✅ Stopped monitoring job {job_id}.")
    else:
        await update.message.reply_text(f"✅ Stopped monitoring job {job_id}.")
    return True

async def check_monitored_jobs(context: ContextTypes.DEFAULT_TYPE):
    """Periodic task to check all monitored jobs"""
    if not MONITORED_JOBS:
        return
    
    # Copy the dict to avoid size changes during iteration
    jobs_to_check = MONITORED_JOBS.copy()
    
    for job_id, job_info in jobs_to_check.items():
        chat_id = job_info["chat_id"]
        last_state = job_info["last_state"]
        
        # Get current job details
        job_details = get_job_details(job_id)
        
        # Skip if error getting job details (could be temporary)
        if "Error" in job_details:
            logger.warning(f"Error checking job {job_id}: {job_details['Error']}")
            continue
        
        current_state = job_details.get("JobState", "UNKNOWN")
        
        # Check if state has changed to a terminal state
        if current_state != last_state and current_state in ["COMPLETED", "CANCELLED", "FAILED", "TIMEOUT"]:
            # Get full job info including resource usage
            resource_usage = get_job_resource_usage(job_id)
            
            # Prepare notification message
            job_name = job_details.get("JobName", "Unknown")
            notification = f"🔔 *Job Completed Notification*\n\n"
            notification += f"*Job ID:* {job_id}\n"
            notification += f"*Job Name:* {job_name}\n"
            notification += f"*Final State:* {current_state}\n"
            
            # Include exit code if available
            if "ExitCode" in resource_usage:
                exit_code = resource_usage["ExitCode"]
                notification += f"*Exit Code:* {exit_code}\n"
                
                # Add interpretation of exit code
                if exit_code == "0:0":
                    notification += "✅ *Job completed successfully*\n"
                else:
                    notification += "❌ *Job failed or had errors*\n"
            
            # Include runtime if available
            if "Elapsed" in resource_usage:
                notification += f"*Run Time:* {resource_usage['Elapsed']}\n"
            elif "RunTime" in job_details:
                notification += f"*Run Time:* {job_details['RunTime']}\n"
            
            # Include basic resource usage if available
            notification += "\n*Resource Usage:*\n"
            for resource_key in ["AveCPU", "MaxRSS", "ConsumedEnergy"]:
                if resource_key in resource_usage:
                    # Format the resource key (e.g., AveCPU -> Average CPU)
                    formatted_key = resource_key
                    if resource_key == "AveCPU":
                        formatted_key = "Average CPU"
                    elif resource_key == "MaxRSS":
                        formatted_key = "Peak Memory"
                    elif resource_key == "ConsumedEnergy":
                        formatted_key = "Energy"
                    
                    notification += f"*{formatted_key}:* {resource_usage[resource_key]}\n"
            
            # Create keyboard with more info button
            keyboard = [[
                InlineKeyboardButton("📋 Detailed Job Info", callback_data=f"jobinfo_{job_id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send notification
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=notification,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
                
                # Remove job from monitored list
                del MONITORED_JOBS[job_id]
                save_monitored_jobs()
                logger.info(f"Job {job_id} notification sent and removed from monitoring")
                
            except Exception as e:
                logger.error(f"Error sending notification for job {job_id}: {e}")
        
        # Update last state for jobs that are still running
        elif current_state != last_state:
            MONITORED_JOBS[job_id]["last_state"] = current_state
            save_monitored_jobs()
            logger.info(f"Job {job_id} state updated to {current_state}")

# ─── Command Handlers ─────────────────────────────────────────────────────────

async def auth_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, callback):
    """Wrapper to check user authorization before executing commands."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(
            "⛔ You are not authorized to use this bot. Contact the administrator."
        )
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return
    
    await callback(update, context)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message when /start is used"""
    await update.message.reply_text(
        "👋 Hello! I'm Green-Boy, your SLURM job monitoring assistant.\n\n"
        "Use /squeue to list your jobs or /help for more commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help information when /help is used"""
    help_text = (
        "📖 *Available commands:*\n"
        "/start - say hello\n"
        "/help - show this message\n"
        "/squeue [FLAGS] - list your jobs\n"
        "  • default: only running (`-t R`)\n"
        "  • e.g. `/squeue -p gpu -n vasp`\n"
        "/cancel <JOBID> - cancel that job\n"
        "/jobinfo <JOBID> - show detailed job information with resource usage\n"
        "/status - show overall cluster status\n"
        "/submit <script> - submit a job script\n"
        "/monitor <JOBID> - monitor a job for completion notifications\n"
        "/unmonitor <JOBID> - stop monitoring a job\n"
        "/monitorlist - list all jobs being monitored\n"
        "/custom <command> [args] - run a custom SLURM command\n"
        "/shutdown - safely shutdown the bot 🔒\n\n"
        "Examples:\n"
        "• `/squeue -p gpu` - jobs on the gpu partition\n"
        "• `/squeue -t PD` - pending jobs\n"
        "• `/cancel 60489632` - cancel job 60489632\n"
        "• `/jobinfo 60489632` - show details and resource usage for job 60489632\n"
        "• `/monitor 60489632` - get notification when job completes\n"
        "• `/custom sacct --jobs=60489632 --format=JobID,State,ExitCode -P` - custom SLURM command\n"
    )
    
    # Add shutdown button for authorized users
    keyboard = []
    user_id = update.effective_user.id
    if is_authorized(user_id):
        keyboard.append([InlineKeyboardButton("🔴 Shutdown Bot", callback_data="shutdown_confirm")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=reply_markup)

async def squeue_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for squeue command"""
    await auth_wrapper(update, context, squeue_command)

async def squeue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /squeue [FLAGS]
    If FLAGS are omitted, defaults to ['-t', 'R'] (running).
    Otherwise, passes whatever FLAGS you include directly to squeue.
    """
    flags = context.args or ["-t", "R"]
    raw = run_squeue(flags)
    
    # Parse and format the output
    try:
        jobs = parse_squeue_output(raw)
        formatted_output, job_ids = format_fancy_job_list(jobs)
    except Exception as e:
        logger.error(f"Error formatting job list: {e}")
        # Fall back to original format if parsing fails
        formatted_output = f"<pre>{raw}</pre>"
        await update.message.reply_text(
            formatted_output,
            parse_mode="HTML"
        )
        return

    # Create an inline keyboard for common actions
    keyboard = [
        [
            InlineKeyboardButton("📊 All Jobs", callback_data="squeue_all"),
            InlineKeyboardButton("⏳ Pending", callback_data="squeue_pending")
        ],
        [
            InlineKeyboardButton("🏃 Running", callback_data="squeue_running"),
            InlineKeyboardButton("🖥️ GPU Jobs", callback_data="squeue_gpu")
        ]
    ]
    
    # Add job ID buttons (but only if we don't have too many)
    if len(job_ids) > 0 and len(job_ids) <= 10:
        for job_id in job_ids:
            keyboard.append([
                InlineKeyboardButton(f"📋 Info for job {job_id}", callback_data=f"jobinfo_{job_id}")
            ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Paginate if necessary
    if len(formatted_output) > MAX_MESSAGE_LENGTH:
        # If the fancy format is too long, fall back to the original format with pagination
        for i, chunk in enumerate(paginate_lines(raw, MAX_MESSAGE_LENGTH)):
            chunk_formatted = f"<pre>{chunk}</pre>"
            if i == 0:
                await update.message.reply_text(chunk_formatted, parse_mode="HTML", reply_markup=reply_markup)
            else:
                await update.message.reply_text(chunk_formatted, parse_mode="HTML")
    else:
        # Send the fancy formatted output
        await update.message.reply_text(formatted_output, parse_mode="Markdown", reply_markup=reply_markup)

async def cancel_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for cancel command"""
    await auth_wrapper(update, context, cancel_command)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cancel <JOBID>  — uses scancel for more reliable job cancellation
    """
    if not context.args:
        await update.message.reply_text("Usage: /cancel <JOBID>")
        return

    jobid = context.args[0]
    
    # Clean the job ID to extract just the numeric part
    # This handles cases like "12345_0" or "12345.batch"
    clean_jobid = re.match(r'(\d+)', jobid)
    if clean_jobid:
        clean_jobid = clean_jobid.group(1)
    else:
        await update.message.reply_text(f"❌ Invalid job ID format: {jobid}")
        return
    
    # First, verify the job exists and belongs to the user
    job_details = get_job_details(clean_jobid)
    if "Error" in job_details:
        await update.message.reply_text(f"❌ Job {jobid} not found or access denied.")
        return
    
    # Try scancel first (more reliable)
    success, output = run_slurm_command(["scancel", clean_jobid])
    
    # If scancel fails, try scontrol cancel as fallback
    if not success:
        success, output = run_slurm_command(["scontrol", "cancel", clean_jobid])
    
    if success:
        # Get job name for confirmation
        job_name = job_details.get("JobName", "Unknown")
        await update.message.reply_text(
            f"✅ Job {jobid} ({job_name}) cancelled successfully."
        )
    else:
        # Provide more detailed error information
        job_state = job_details.get("JobState", "Unknown")
        error_msg = f"❌ Error cancelling job {jobid}:\n{output}\n\n"
        error_msg += f"Job State: {job_state}\n"
        
        # Add helpful context based on job state
        if job_state in ["COMPLETED", "CANCELLED", "FAILED"]:
            error_msg += "ℹ️ Note: This job has already finished and cannot be cancelled."
        elif job_state == "PENDING":
            error_msg += "ℹ️ Note: If cancellation failed, the job might have already started running."
        
        await update.message.reply_text(error_msg)

async def jobinfo_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for jobinfo command"""
    await auth_wrapper(update, context, jobinfo_command)

async def jobinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /jobinfo <JOBID>  — show detailed information about a job including CPU and memory usage
    """
    if not context.args:
        await update.message.reply_text("Usage: /jobinfo <JOBID>")
        return

    jobid = context.args[0]
    details = get_job_details(jobid)
    
    if "Error" in details:
        await update.message.reply_text(f"❌ Error retrieving job info: {details['Error']}")
        return
    
    # Format job details
    info_text = f"📋 *Job Information for {jobid}*\n\n"
    
    # Key details to include (in a specific order)
    key_details = [
        ("JobId", "Job ID"),
        ("JobName", "Name"),
        ("UserId", "User"),
        ("JobState", "State"),
        ("Partition", "Partition"),
        ("TimeLimit", "Time Limit"),
        ("RunTime", "Runtime"),
        ("NumNodes", "Nodes"),
        ("NumCPUs", "CPUs"),
        ("NodeList", "Node List")
    ]
    
    for key, label in key_details:
        if key in details:
            info_text += f"*{label}:* {details[key]}\n"
    
    # Get resource usage for any job state
    job_state = details.get("JobState", "UNKNOWN")
    resource_usage = get_job_resource_usage(jobid)
    
    if resource_usage:
        info_text += "\n*Resource Usage:*\n"
        
        # Add CPU usage
        if "AveCPU" in resource_usage:
            info_text += f"*Average CPU Usage:* {resource_usage['AveCPU']}\n"
        
        # Add CPU time if available
        if "CPUTime" in resource_usage:
            info_text += f"*CPU Time:* {resource_usage['CPUTime']}\n"
        
        # Add CPU allocation and per-task usage for running jobs
        if "AllocatedCPUs" in resource_usage and resource_usage["AllocatedCPUs"] > 0:
            info_text += f"*Allocated CPUs:* {resource_usage['AllocatedCPUs']}\n"
            
            # Display detailed per-task CPU usage if available
            if "tasks" in resource_usage and resource_usage["tasks"]:
                info_text += "\n*Per-Task CPU Usage:*\n"
                for i, task in enumerate(resource_usage["tasks"]):
                    if i >= 5:  # Limit to first 5 tasks
                        break
                    task_id = task.get("TaskID", "Unknown")
                    cpu_usage = task.get("AveCPU", "Unknown")
                    memory = task.get("AveRSS", "Unknown")
                    info_text += f"*Task {task_id}:* CPU: {cpu_usage}, Memory: {memory}\n"
                
                if len(resource_usage["tasks"]) > 5:
                    info_text += f"_...and {len(resource_usage['tasks']) - 5} more tasks..._\n"
        
        # Add memory usage
        if "AveRSS" in resource_usage:
            info_text += f"*Average Memory (RSS):* {resource_usage['AveRSS']}\n"
        if "MaxRSS" in resource_usage:
            info_text += f"*Peak Memory (RSS):* {resource_usage['MaxRSS']}\n"
        if "AveVMSize" in resource_usage:
            info_text += f"*Average Virtual Memory:* {resource_usage['AveVMSize']}\n"
        if "MaxVMSize" in resource_usage:
            info_text += f"*Peak Virtual Memory:* {resource_usage['MaxVMSize']}\n"
        
        # Add CPU frequency if available
        if "AveCPUFreq" in resource_usage:
            info_text += f"*Average CPU Frequency:* {resource_usage['AveCPUFreq']}\n"
        
        # Add energy consumption if available
        if "ConsumedEnergy" in resource_usage:
            info_text += f"*Energy Consumption:* {resource_usage['ConsumedEnergy']}\n"
            
        # Add exit code for completed jobs
        if job_state in ["COMPLETED", "CANCELLED", "FAILED", "TIMEOUT"]:
            if "ExitCode" in resource_usage:
                exit_code = resource_usage['ExitCode']
                info_text += f"*Exit Code:* {exit_code}\n"
                
                # Add interpretation of exit code
                if exit_code == "0:0":
                    info_text += "✅ *Job completed successfully*\n"
                else:
                    info_text += "❌ *Job failed or had errors*\n"
                    
    elif job_state == "RUNNING":
        info_text += "\n*Resource Usage:*\n"
        info_text += "_Resource usage information not available. The job may have just started._\n"
    elif job_state == "PENDING":
        info_text += "\n*Resource Usage:*\n"
        info_text += "_Resource usage information not available for pending jobs._\n"
    
    # Add buttons
    keyboard = []
    user_id = update.effective_user.id
    
    # First row: Cancel job button
    keyboard.append([InlineKeyboardButton("❌ Cancel Job", callback_data=f"cancel_{jobid}")])
    
    # Second row: CPU and Memory button (for running jobs)
    if job_state == "RUNNING":
        keyboard.append([InlineKeyboardButton("📊 Detailed CPU & Memory", callback_data=f"cpu_mem_{jobid}")])
    
    # Add monitoring buttons if job is not completed
    if job_state not in ["COMPLETED", "CANCELLED", "FAILED", "TIMEOUT"]:
        # Check if job is being monitored
        if jobid in MONITORED_JOBS and MONITORED_JOBS[jobid]["user_id"] == user_id:
            keyboard.append([InlineKeyboardButton("🔕 Stop Monitoring", callback_data=f"unmonitor_{jobid}")])
        else:
            keyboard.append([InlineKeyboardButton("🔔 Monitor Completion", callback_data=f"monitor_{jobid}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(info_text, parse_mode="Markdown", reply_markup=reply_markup)

async def status_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for status command"""
    await auth_wrapper(update, context, status_command)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /status  — show overall cluster status
    """
    raw_status = get_cluster_status()
    
    # Try to format the status in a prettier way
    try:
        formatted = format_cluster_status(raw_status)
    except Exception as e:
        logger.error(f"Error formatting cluster status: {e}")
        # Fall back to original format
        formatted = f"🖥️ *Cluster Status*\n\n<pre>{raw_status}</pre>"
        await update.message.reply_text(formatted, parse_mode="HTML")
        return
    
    # Add shutdown button for authorized users
    keyboard = []
    user_id = update.effective_user.id
    if is_authorized(user_id):
        keyboard.append([InlineKeyboardButton("🔴 Shutdown Bot", callback_data="shutdown_confirm")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    # Send the formatted status
    await update.message.reply_text(formatted, parse_mode="Markdown", reply_markup=reply_markup)

async def submit_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for submit command"""
    await auth_wrapper(update, context, submit_command)

async def submit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /submit <script>  — submit a job script
    """
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /submit <script_path>\n\n"
            "Example: `/submit /path/to/my_job.sh`"
        )
        return
    
    script_path = context.args[0]
    success, output = run_slurm_command(["sbatch", script_path])
    
    if success:
        # Extract job ID from the output
        job_id = None
        if "Submitted batch job" in output:
            try:
                job_id = output.split()[-1]
            except:
                pass
        
        msg = f"✅ Job submitted successfully!\n{output}"
        
        # Add keyboard with job status and monitoring buttons
        if job_id:
            keyboard = [
                [InlineKeyboardButton("📋 Check Status", callback_data=f"jobinfo_{job_id}")],
                [InlineKeyboardButton("🔔 Monitor Completion", callback_data=f"monitor_{job_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(msg)
    else:
        await update.message.reply_text(f"❌ Error submitting job:\n{output}")

async def shutdown_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for shutdown command"""
    await auth_wrapper(update, context, shutdown_command)

async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /shutdown - safely shutdown the bot (authorized users only)
    """
    # Double-check authorization (extra security for shutdown)
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ You are not authorized to shutdown the bot.")
        logger.warning(f"Unauthorized shutdown attempt by user {user_id}")
        return
    
    # Get user info for logging
    user_info = update.effective_user.username or update.effective_user.first_name or str(user_id)
    
    # Send confirmation message with buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Shutdown", callback_data="shutdown_execute"),
            InlineKeyboardButton("❌ Cancel", callback_data="shutdown_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔴 *Bot Shutdown Confirmation*\n\n"
        f"User: @{user_info}\n"
        f"PID: {os.getpid()}\n\n"
        f"Are you sure you want to shutdown the Green-Boy bot?\n\n"
        f"⚠️ *Warning*: This will stop the bot completely. "
        f"You'll need to restart it manually on the cluster.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# New monitoring commands
async def monitor_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for monitor command"""
    await auth_wrapper(update, context, monitor_command)

async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /monitor <JOBID> - Start monitoring a job for completion notification
    """
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /monitor <JOBID>")
        return
    
    job_id = context.args[0]
    await monitor_job(update, context, job_id)

async def unmonitor_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for unmonitor command"""
    await auth_wrapper(update, context, unmonitor_command)

async def unmonitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /unmonitor <JOBID> - Stop monitoring a job
    """
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /unmonitor <JOBID>")
        return
    
    job_id = context.args[0]
    await stop_monitoring_job(update, context, job_id)

async def monitorlist_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for monitorlist command"""
    await auth_wrapper(update, context, monitorlist_command)

async def monitorlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /monitorlist - List all jobs being monitored
    """
    user_id = update.effective_user.id
    
    # Filter jobs for this user (admins can see all)
    user_jobs = {}
    for job_id, job_info in MONITORED_JOBS.items():
        if job_info["user_id"] == user_id or is_authorized(user_id):
            user_jobs[job_id] = job_info
    
    if not user_jobs:
        await update.message.reply_text("No jobs are currently being monitored.")
        return
    
    # Generate list of monitored jobs
    reply = "📋 *Monitored Jobs:*\n\n"
    
    for job_id, job_info in user_jobs.items():
        # Get current job state
        try:
            job_details = get_job_details(job_id)
            current_state = job_details.get("JobState", "UNKNOWN")
            job_name = job_details.get("JobName", "Unknown")
        except:
            current_state = "Error"
            job_name = "Unknown"
        
        # Get state emoji
        state_emoji = get_state_emoji(current_state)
        
        reply += f"{state_emoji} *Job {job_id}*: `{job_name}`\n"
        reply += f"    • State: `{current_state}`\n"
        reply += f"    • Since: `{job_info.get('added_time', 'Unknown')}`\n\n"
    
    # Add keyboard with monitor/unmonitor buttons
    keyboard = []
    if len(user_jobs) <= 5:  # Only show buttons if list is not too long
        for job_id in user_jobs.keys():
            keyboard.append([
                InlineKeyboardButton(f"📋 Info: {job_id}", callback_data=f"jobinfo_{job_id}"),
                InlineKeyboardButton(f"🛑 Stop: {job_id}", callback_data=f"unmonitor_{job_id}")
            ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(reply, parse_mode="Markdown", reply_markup=reply_markup)

# Custom command functionality
async def custom_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for custom command"""
    await auth_wrapper(update, context, custom_command)

async def custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /custom <command> [args] - Run a custom SLURM command
    
    Only a whitelist of safe commands is allowed
    """
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /custom <command> [args]\n\n"
            "Allowed commands: sacct, sinfo, squeue, sstat, sprio\n"
            "Example: `/custom sacct --jobs=12345 --format=JobID,State,ExitCode -P`"
        )
        return
    
    # Whitelist of safe commands
    # Note: commands like srun, sbatch, scancel are excluded for safety
    ALLOWED_COMMANDS = ["sacct", "sinfo", "squeue", "sstat", "sprio"]
    
    cmd = context.args[0].lower()
    if cmd not in ALLOWED_COMMANDS:
        await update.message.reply_text(
            f"❌ Command '{cmd}' is not allowed.\n"
            f"Allowed commands: {', '.join(ALLOWED_COMMANDS)}"
        )
        return
    
    # Build the command 
    # Note: context.args[0] is the command, context.args[1:] are the arguments
    slurm_cmd = [cmd] + context.args[1:]
    
    # Run the command
    success, output = run_slurm_command(slurm_cmd)
    
    # Paginate if necessary
    for i, chunk in enumerate(paginate_lines(output, MAX_MESSAGE_LENGTH)):
        formatted = f"<pre>{chunk}</pre>"
        await update.message.reply_text(formatted, parse_mode="HTML")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks from inline keyboards."""
    query = update.callback_query
    await query.answer()
    
    # Check authorization
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await query.edit_message_text("⛔ You are not authorized to use this bot.")
        return
    
    data = query.data
    
    # Handle squeue filter buttons
    if data.startswith("squeue_"):
        filter_type = data.split("_")[1]
        flags = []
        
        if filter_type == "all":
            flags = []
        elif filter_type == "pending":
            flags = ["-t", "PD"]
        elif filter_type == "running":
            flags = ["-t", "R"]
        elif filter_type == "gpu":
            flags = ["-p", "gpu"]
        
        raw = run_squeue(flags)
        
        # Parse and format the output
        try:
            jobs = parse_squeue_output(raw)
            formatted_output, job_ids = format_fancy_job_list(jobs)
        except Exception as e:
            logger.error(f"Error formatting job list: {e}")
            # Fall back to original format if parsing fails
            formatted_output = f"<pre>{raw}</pre>"
            
            # Create the same keyboard for consistency
            keyboard = [
                [
                    InlineKeyboardButton("📊 All Jobs", callback_data="squeue_all"),
                    InlineKeyboardButton("⏳ Pending", callback_data="squeue_pending")
                ],
                [
                    InlineKeyboardButton("🏃 Running", callback_data="squeue_running"),
                    InlineKeyboardButton("🖥️ GPU Jobs", callback_data="squeue_gpu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                formatted_output,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return
        
        # Create keyboard with filter buttons
        keyboard = [
            [
                InlineKeyboardButton("📊 All Jobs", callback_data="squeue_all"),
                InlineKeyboardButton("⏳ Pending", callback_data="squeue_pending")
            ],
            [
                InlineKeyboardButton("🏃 Running", callback_data="squeue_running"),
                InlineKeyboardButton("🖥️ GPU Jobs", callback_data="squeue_gpu")
            ]
        ]
        
        # Add job ID buttons (but only if we don't have too many)
        if len(job_ids) > 0 and len(job_ids) <= 10:
            for job_id in job_ids:
                keyboard.append([
                    InlineKeyboardButton(f"📋 Info for job {job_id}", callback_data=f"jobinfo_{job_id}")
                ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Paginate if necessary
        if len(formatted_output) > MAX_MESSAGE_LENGTH:
            # If the fancy format is too long, fall back to the original format with pagination
            for i, chunk in enumerate(paginate_lines(raw, MAX_MESSAGE_LENGTH)):
                chunk_formatted = f"<pre>{chunk}</pre>"
                if i == 0:
                    await query.edit_message_text(
                        chunk_formatted,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                else:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=chunk_formatted,
                        parse_mode="HTML"
                    )
        else:
            # Send the fancy formatted output
            await query.edit_message_text(
                formatted_output,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    
    # Handle cancel job button (improved version)
    elif data.startswith("cancel_"):
        job_id = data.split("_")[1]
        
        # Clean the job ID to extract just the numeric part
        clean_jobid = re.match(r'(\d+)', job_id)
        if clean_jobid:
            clean_jobid = clean_jobid.group(1)
        else:
            await query.edit_message_text(
                f"❌ Invalid job ID format: {job_id}",
                parse_mode="Markdown"
            )
            return
        
        # First verify the job exists
        job_details = get_job_details(clean_jobid)
        if "Error" in job_details:
            await query.edit_message_text(
                f"❌ Job {job_id} not found or access denied.",
                parse_mode="Markdown"
            )
            return
        
        # Try scancel first, then scontrol cancel as fallback
        success, output = run_slurm_command(["scancel", clean_jobid])
        if not success:
            success, output = run_slurm_command(["scontrol", "cancel", clean_jobid])
        
        if success:
            job_name = job_details.get("JobName", "Unknown")
            await query.edit_message_text(
                f"✅ Job {job_id} ({job_name}) cancelled successfully.",
                parse_mode="Markdown"
            )
        else:
            job_state = job_details.get("JobState", "Unknown")
            error_msg = f"❌ Error cancelling job {job_id}:\n{output}\n\n"
            error_msg += f"Job State: {job_state}"
            
            if job_state in ["COMPLETED", "CANCELLED", "FAILED"]:
                error_msg += "\n\nℹ️ Note: This job has already finished."
            
            await query.edit_message_text(
                error_msg,
                parse_mode="Markdown"
            )
    
    # Handle monitoring buttons
    elif data.startswith("monitor_"):
        job_id = data.split("_")[1]
        await monitor_job(update, context, job_id)
    
    # Handle unmonitor buttons
    elif data.startswith("unmonitor_"):
        job_id = data.split("_")[1]
        await stop_monitoring_job(update, context, job_id)
    
    # Handle shutdown confirmation button
    elif data == "shutdown_confirm":
        # Double-check authorization (extra security)
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await query.edit_message_text("⛔ You are not authorized to shutdown the bot.")
            return
        
        # Get user info for logging
        user_info = update.effective_user.username or update.effective_user.first_name or str(user_id)
        
        # Show confirmation with buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Shutdown", callback_data="shutdown_execute"),
                InlineKeyboardButton("❌ Cancel", callback_data="shutdown_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔴 *Bot Shutdown Confirmation*\n\n"
            f"User: @{user_info}\n"
            f"PID: {os.getpid()}\n\n"
            f"Are you sure you want to shutdown the Green-Boy bot?\n\n"
            f"⚠️ *Warning*: This will stop the bot completely. "
            f"You'll need to restart it manually on the cluster.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    # Handle shutdown execution
    elif data == "shutdown_execute":
        # Triple-check authorization (extra security for execution)
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await query.edit_message_text("⛔ You are not authorized to shutdown the bot.")
            return
        
        # Get user info for logging
        user_info = update.effective_user.username or update.effective_user.first_name or str(user_id)
        
        # Log the shutdown
        logger.warning(f"Bot shutdown initiated by user {user_info} (ID: {user_id})")
        
        # Send final message
        await query.edit_message_text(
            f"🔴 *Bot Shutdown Initiated*\n\n"
            f"Shutting down Green-Boy bot...\n"
            f"Initiated by: @{user_info}\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"✅ Bot will terminate in 3 seconds.\n"
            f"🔄 To restart, run the bot script on the cluster again.",
            parse_mode="Markdown"
        )
        
        # Give time for the message to be sent
        await asyncio.sleep(1)
        
        # Cleanup and shutdown
        try:
            # Clean up webhook
            import requests
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True},
                timeout=5
            )
            print("Webhook cleared during shutdown")
        except Exception as e:
            print(f"Could not clear webhook during shutdown: {e}")
        
        # Stop the application gracefully
        print(f"Bot shutdown initiated by {user_info}")
        await context.application.stop()
        await context.application.shutdown()
        
        # Release locks
        release_locks()
        
        # Force exit
        os._exit(0)
    
    # Handle shutdown cancellation
    elif data == "shutdown_cancel":
        await query.edit_message_text(
            "✅ *Shutdown Cancelled*\n\n"
            "The bot will continue running normally.",
            parse_mode="Markdown"
        )
    
    # Handle jobinfo button
    elif data.startswith("jobinfo_"):
        job_id = data.split("_")[1]
        details = get_job_details(job_id)
        
        if "Error" in details:
            await query.edit_message_text(
                f"❌ Error retrieving job info: {details['Error']}",
                parse_mode="Markdown"
            )
            return
        
        # Format job details
        info_text = f"📋 *Job Information for {job_id}*\n\n"
        
        # Key details to include
        key_details = [
            ("JobId", "Job ID"),
            ("JobName", "Name"),
            ("UserId", "User"),
            ("JobState", "State"),
            ("Partition", "Partition"),
            ("TimeLimit", "Time Limit"),
            ("RunTime", "Runtime"),
            ("NumNodes", "Nodes"),
            ("NumCPUs", "CPUs"),
            ("NodeList", "Node List")
        ]
        
        for key, label in key_details:
            if key in details:
                info_text += f"*{label}:* {details[key]}\n"
        
        # Get resource usage for any job state
        job_state = details.get("JobState", "UNKNOWN")
        resource_usage = get_job_resource_usage(job_id)
        
        if resource_usage:
            info_text += "\n*Resource Usage:*\n"
            
            # Add CPU usage
            if "AveCPU" in resource_usage:
                info_text += f"*Average CPU Usage:* {resource_usage['AveCPU']}\n"
            
            # Add CPU time if available
            if "CPUTime" in resource_usage:
                info_text += f"*CPU Time:* {resource_usage['CPUTime']}\n"
            
            # Add CPU allocation and per-task usage for running jobs
            if "AllocatedCPUs" in resource_usage and resource_usage["AllocatedCPUs"] > 0:
                info_text += f"*Allocated CPUs:* {resource_usage['AllocatedCPUs']}\n"
                
                # Display detailed per-task CPU usage if available
                if "tasks" in resource_usage and resource_usage["tasks"]:
                    info_text += "\n*Per-Task CPU Usage:*\n"
                    for i, task in enumerate(resource_usage["tasks"]):
                        if i >= 5:  # Limit to first 5 tasks
                            break
                        task_id = task.get("TaskID", "Unknown")
                        cpu_usage = task.get("AveCPU", "Unknown")
                        memory = task.get("AveRSS", "Unknown")
                        info_text += f"*Task {task_id}:* CPU: {cpu_usage}, Memory: {memory}\n"
                    
                    if len(resource_usage["tasks"]) > 5:
                        info_text += f"_...and {len(resource_usage['tasks']) - 5} more tasks..._\n"
            
            # Add memory usage
            if "AveRSS" in resource_usage:
                info_text += f"*Average Memory (RSS):* {resource_usage['AveRSS']}\n"
            if "MaxRSS" in resource_usage:
                info_text += f"*Peak Memory (RSS):* {resource_usage['MaxRSS']}\n"
            if "AveVMSize" in resource_usage:
                info_text += f"*Average Virtual Memory:* {resource_usage['AveVMSize']}\n"
            if "MaxVMSize" in resource_usage:
                info_text += f"*Peak Virtual Memory:* {resource_usage['MaxVMSize']}\n"
            
            # Add CPU frequency if available
            if "AveCPUFreq" in resource_usage:
                info_text += f"*Average CPU Frequency:* {resource_usage['AveCPUFreq']}\n"
            
            # Add energy consumption if available
            if "ConsumedEnergy" in resource_usage:
                info_text += f"*Energy Consumption:* {resource_usage['ConsumedEnergy']}\n"
                
            # Add exit code for completed jobs
            if job_state in ["COMPLETED", "CANCELLED", "FAILED", "TIMEOUT"]:
                if "ExitCode" in resource_usage:
                    exit_code = resource_usage['ExitCode']
                    info_text += f"*Exit Code:* {exit_code}\n"
                    
                    # Add interpretation of exit code
                    if exit_code == "0:0":
                        info_text += "✅ *Job completed successfully*\n"
                    else:
                        info_text += "❌ *Job failed or had errors*\n"
                        
        elif job_state == "RUNNING":
            info_text += "\n*Resource Usage:*\n"
            info_text += "_Resource usage information not available. The job may have just started._\n"
        elif job_state == "PENDING":
            info_text += "\n*Resource Usage:*\n"
            info_text += "_Resource usage information not available for pending jobs._\n"
        
        # Add buttons
        keyboard = []
        
        # First row: Cancel job button
        keyboard.append([InlineKeyboardButton("❌ Cancel Job", callback_data=f"cancel_{job_id}")])
        
        # Second row: CPU and Memory button (for running jobs)
        if job_state == "RUNNING":
            keyboard.append([InlineKeyboardButton("📊 Detailed CPU & Memory", callback_data=f"cpu_mem_{job_id}")])
        
        # Add monitoring buttons if job is not completed
        if job_state not in ["COMPLETED", "CANCELLED", "FAILED", "TIMEOUT"]:
            # Check if job is being monitored
            if job_id in MONITORED_JOBS and MONITORED_JOBS[job_id]["user_id"] == user_id:
                keyboard.append([InlineKeyboardButton("🔕 Stop Monitoring", callback_data=f"unmonitor_{job_id}")])
            else:
                keyboard.append([InlineKeyboardButton("🔔 Monitor Completion", callback_data=f"monitor_{job_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            info_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    # Handle CPU and Memory button
    elif data.startswith("cpu_mem_"):
        job_id = data.split("_")[2]
        processes_info = get_job_processes(job_id)
        
        # Format the message with the processes info
        info_text = f"📊 *Detailed CPU and Memory Usage for Job {job_id}*\n\n"
        
        # Get job details for the back button
        details = get_job_details(job_id)
        
        # Add a pre-formatted block with process information
        formatted_processes = f"<pre>{processes_info}</pre>"
        
        # Create a back button to return to job info
        keyboard = [[InlineKeyboardButton("⬅️ Back to Job Info", callback_data=f"jobinfo_{job_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send response - handle potential HTML issues by using different formatting
        try:
            await query.edit_message_text(
                info_text + formatted_processes,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except Exception as e:
            # If HTML formatting fails, try plain text
            logger.error(f"Error formatting CPU and memory info: {e}")
            
            # Escape any problematic HTML characters and send as plain text
            info_text = f"📊 Detailed CPU and Memory Usage for Job {job_id}\n\n"
            info_text += "```\n" + processes_info + "\n```"
            
            await query.edit_message_text(
                info_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

# ─── Error Handler ─────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram-python-bot library."""
    # Log the error
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Extract error details
    error_type = type(context.error).__name__
    error_message = str(context.error)
    
    # Handle Conflict errors specially
    if isinstance(context.error, Conflict):
        logger.error("Conflict error detected - this might indicate multiple bot instances")
        # Note: Don't exit here, as this would terminate the error handler not the application
        # Instead, log the issue and let the main polling loop handle it
    
    # Get the user that triggered the error
    if update and hasattr(update, 'effective_user'):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        logger.error(f"Error triggered by user: {user_id}")
    
    # Inform user of the error if we have an update object
    if update and hasattr(update, 'effective_message') and update.effective_message:
        await update.effective_message.reply_text(
            f"⚠️ An error occurred: {error_type}\n"
            "The bot administrator has been notified."
        )

# ─── Bot Setup ────────────────────────────────────────────────────────────────

def main():
    """Main function to start the bot with enhanced protection against multiple instances"""
    
    # Step 1: Kill any existing instances of the bot
    print("=" * 60)
    print("STARTING GREEN-BOY BOT WITH STRONG CONFLICT PROTECTION")
    print("=" * 60)
    
    # First, validate the bot token minimally
    if not BOT_TOKEN or len(BOT_TOKEN) < 20:
        print("ERROR: Invalid bot token. Please set TELEGRAM_BOT_TOKEN environment variable.")
        return 1
    
    # Kill any existing processes first
    killed_processes = kill_running_bot_processes()
    if killed_processes > 0:
        print(f"Killed {killed_processes} existing bot processes")
        # Wait to make sure everything is properly terminated
        print("Waiting 10 seconds to ensure processes are fully terminated...")
        time.sleep(10)
    
    # Step 2: Check if another instance is still running
    if not check_running_instance():
        print("ERROR: Another instance of the bot is still running despite cleanup. Exiting.")
        return 1
    
    # Step 3: Aggressively clean up any existing webhooks
    if not aggressive_webhook_cleanup():
        print("WARNING: Webhook cleanup might not have been successful")
        # Continue anyway, but with a warning
    
    # Step 4: Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Print starting message
    print("Starting Green-Boy created by https://github.com/adamlaho/")
    print(f"Process PID: {os.getpid()}")
    
    # Set up the event loop explicitly
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Load saved monitored jobs
    load_monitored_jobs()
    
    # Retry mechanism for bot startup
    max_startup_attempts = 5
    for startup_attempt in range(max_startup_attempts):
        try:
            # Use the ApplicationBuilder with more conservative settings
            application = (ApplicationBuilder()
                .token(BOT_TOKEN)
                .connect_timeout(30.0)
                .read_timeout(30.0)
                .get_updates_connect_timeout(30.0)
                .get_updates_read_timeout(30.0)
                .get_updates_connection_pool_size(1)  # Use just one connection
                .connection_pool_size(4)  # Keep connection pool small
                .build())
            
            # Register command handlers
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(CommandHandler("squeue", squeue_command_wrapper))
            application.add_handler(CommandHandler("cancel", cancel_command_wrapper))
            application.add_handler(CommandHandler("jobinfo", jobinfo_command_wrapper))
            application.add_handler(CommandHandler("status", status_command_wrapper))
            application.add_handler(CommandHandler("submit", submit_command_wrapper))
            application.add_handler(CommandHandler("shutdown", shutdown_command_wrapper))
            
            # Register new monitoring command handlers
            application.add_handler(CommandHandler("monitor", monitor_command_wrapper))
            application.add_handler(CommandHandler("unmonitor", unmonitor_command_wrapper))
            application.add_handler(CommandHandler("monitorlist", monitorlist_command_wrapper))
            
            # Register custom command handler
            application.add_handler(CommandHandler("custom", custom_command_wrapper))
            
            # Register callback query handler for buttons
            application.add_handler(CallbackQueryHandler(button_callback))
            
            # Register error handler
            application.add_error_handler(error_handler)
            
            # Set up the job monitoring background task
            job_queue = application.job_queue
            job_queue.run_repeating(check_monitored_jobs, interval=60, first=10)
            
            # Delete webhook once more for extreme paranoia
            try:
                import requests
                response = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
                    json={"drop_pending_updates": True},
                    timeout=20
                )
                print(f"Final webhook cleanup: {response.status_code}")
                
                # Sleep a bit to let API fully process
                time.sleep(5)
            except Exception as e:
                print(f"Final webhook cleanup failed: {e}")
            
            # Print startup message
            print("Green-Boy bot started successfully!")
            print(f"Authorized users: {AUTHORIZED_USERS if AUTHORIZED_USERS else 'All users allowed'}")
            print(f"Running with PID: {os.getpid()}")
            print("Press Ctrl+C to stop the bot")
            
            # Run the bot with conflict handling
            try:
                # Use a more conservative approach with explicit update limits
                application.run_polling(
                    drop_pending_updates=True, 
                    allowed_updates=["message", "callback_query"],
                    close_loop=False,  # Don't close the event loop
                    poll_interval=2.0,  # Poll even slower
                    timeout=30,        # Larger timeout
                    read_timeout=30,   # Explicit read timeout
                    connect_timeout=30, # Explicit connect timeout
                    bootstrap_retries=10, # More bootstrap retries
                    pool_timeout=5.0   # Pool timeout
                )
                break  # If we get here, the bot ran successfully
                
            except Conflict as e:
                print(f"Telegram Conflict Error (attempt {startup_attempt + 1}): {e}")
                if startup_attempt < max_startup_attempts - 1:
                    print("This usually means another bot instance is running.")
                    print("Cleaning up and waiting before retry...")
                    
                    # Run even more aggressive cleanup
                    kill_running_bot_processes()
                    aggressive_webhook_cleanup()
                    
                    # Sleep even longer for conflicts
                    wait_time = 120 + (startup_attempt * 60)  # 2min, 3min, 4min, etc.
                    print(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    print("Maximum startup attempts reached.")
                    print("Please run the telegram_api_reset.sh script and wait a few minutes before trying again.")
                    release_locks()
                    return 1
                    
            except NetworkError as e:
                print(f"Network Error (attempt {startup_attempt + 1}): {e}")
                if startup_attempt < max_startup_attempts - 1:
                    wait_time = 30 + (startup_attempt * 30)
                    print(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    print("Network issues persist. Please check your connection.")
                    release_locks()
                    return 1
                    
        except Exception as e:
            print(f"ERROR during startup attempt {startup_attempt + 1}: {e}")
            import traceback
            traceback.print_exc()
            
            if startup_attempt < max_startup_attempts - 1:
                wait_time = 30 + (startup_attempt * 30)
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("All startup attempts failed.")
                release_locks()
                return 1
    
    # Cleanup on normal exit
    cleanup_on_exit()
    return 0


if __name__ == "__main__":
    sys.exit(main())#!/usr/bin/env python3
