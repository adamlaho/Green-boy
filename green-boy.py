#!/usr/bin/env python3
"""
Green-Boy: A lightweight Telegram bot for SLURM job monitoring
with enhanced resource usage monitoring capabilities
"""
import os
import subprocess
import logging
import sys
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# ─── Configuration ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set")

# Optional authorized users (comma-separated list of user IDs)
AUTH_USERS_STR = os.getenv("GREENBOY_AUTH_USERS", "")
AUTHORIZED_USERS = [int(user_id.strip()) for user_id in AUTH_USERS_STR.split(",") if user_id.strip()]

# Max chars per message
MAX_MESSAGE_LENGTH = 3500

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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
        return True, result.stdout or "(command completed successfully)"
    except subprocess.CalledProcessError as e:
        logger.exception(f"Command {' '.join(cmd)} failed")
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
            "--format=JobID,State,ExitCode,AveCPU,MaxRSS,AveRSS,MaxVMSize,AveVMSize,CPUTime,ConsumedEnergy",
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
        "/submit <script> - submit a job script\n\n"
        "Examples:\n"
        "• `/squeue -p gpu` - jobs on the gpu partition\n"
        "• `/squeue -t PD` - pending jobs\n"
        "• `/cancel 60489632` - cancel job 60489632\n"
        "• `/jobinfo 60489632` - show details and resource usage for job 60489632\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

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
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Paginate if necessary
    for i, chunk in enumerate(paginate_lines(raw, MAX_MESSAGE_LENGTH)):
        formatted = f"<pre>{chunk}</pre>"
        # Only add the keyboard to the first message
        if i == 0:
            await update.message.reply_text(formatted, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await update.message.reply_text(formatted, parse_mode="HTML")

async def cancel_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for cancel command"""
    await auth_wrapper(update, context, cancel_command)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cancel <JOBID>  — uses `scontrol cancel JOBID`
    """
    if not context.args:
        await update.message.reply_text("Usage: /cancel <JOBID>")
        return

    jobid = context.args[0]
    success, output = run_slurm_command(["scontrol", "cancel", jobid])
    
    if success:
        await update.message.reply_text(f"✅ Job {jobid} cancelled.")
    else:
        await update.message.reply_text(f"❌ Error cancelling job {jobid}:\n{output}")

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
    elif job_state == "RUNNING":
        info_text += "\n*Resource Usage:*\n"
        info_text += "_Resource usage information not available. The job may have just started._\n"
    elif job_state == "PENDING":
        info_text += "\n*Resource Usage:*\n"
        info_text += "_Resource usage information not available for pending jobs._\n"
    
    # Add buttons
    keyboard = []
    
    # First row: Cancel job button
    keyboard.append([InlineKeyboardButton("❌ Cancel Job", callback_data=f"cancel_{jobid}")])
    
    # Second row: CPU and Memory button (for running jobs)
    if job_state == "RUNNING":
        keyboard.append([InlineKeyboardButton("📊 Detailed CPU & Memory", callback_data=f"cpu_mem_{jobid}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(info_text, parse_mode="Markdown", reply_markup=reply_markup)

async def status_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Authorization wrapper for status command"""
    await auth_wrapper(update, context, status_command)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /status  — show overall cluster status
    """
    status = get_cluster_status()
    
    formatted = f"🖥️ *Cluster Status*\n\n<pre>{status}</pre>"
    await update.message.reply_text(formatted, parse_mode="HTML")

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
        
        # Add keyboard to check job status
        if job_id:
            keyboard = [[InlineKeyboardButton("📋 Check Status", callback_data=f"jobinfo_{job_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(msg)
    else:
        await update.message.reply_text(f"❌ Error submitting job:\n{output}")

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
        
        for i, chunk in enumerate(paginate_lines(raw, MAX_MESSAGE_LENGTH)):
            formatted = f"<pre>{chunk}</pre>"
            if i == 0:
                await query.edit_message_text(formatted, parse_mode="HTML", reply_markup=reply_markup)
            else:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=formatted,
                    parse_mode="HTML"
                )
    
    # Handle cancel job button
    elif data.startswith("cancel_"):
        job_id = data.split("_")[1]
        success, output = run_slurm_command(["scontrol", "cancel", job_id])
        
        if success:
            await query.edit_message_text(
                f"✅ Job {job_id} cancelled successfully.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"❌ Error cancelling job {job_id}:\n{output}",
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

# ─── Bot Setup ────────────────────────────────────────────────────────────────

def main():
    """Main function to start the bot"""
    # Print starting message
    print("Starting Green-Boy created by adamlaho")
    
    # Set up the event loop explicitly
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Use subprocess to clean up webhooks without asyncio
    try:
        import requests
        print("Clearing webhook...")
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            json={"drop_pending_updates": True}
        )
        print("Webhook cleared successfully")
    except Exception as e:
        print(f"Could not clear webhook using requests: {e}")
        print("Will try clearing webhook during startup")
    
    try:
        # Build application
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Register command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("squeue", squeue_command_wrapper))
        application.add_handler(CommandHandler("cancel", cancel_command_wrapper))
        application.add_handler(CommandHandler("jobinfo", jobinfo_command_wrapper))
        application.add_handler(CommandHandler("status", status_command_wrapper))
        application.add_handler(CommandHandler("submit", submit_command_wrapper))
        
        # Register callback query handler for buttons
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Print startup message
        print("Green-Boy bot started successfully!")
        print(f"Authorized users: {AUTHORIZED_USERS if AUTHORIZED_USERS else 'All users allowed'}")
        print(f"Running with PID: {os.getpid()}")
        
        # Run the bot with the simplest possible parameters
        application.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()
