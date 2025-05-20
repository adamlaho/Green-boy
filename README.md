![AMLP Logo](green_boy_logo.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![SLURM](https://img.shields.io/badge/SLURM-compatible-brightgreen.svg)](https://slurm.schedmd.com/)

## Navigation

| [📋 Overview](#overview) | [🚀 Features](#features) | [⚙️ Installation](#installation) | [📝 Usage](#usage) | [🔍 Commands](#available-commands) |
|--------------------------|--------------------------|----------------------------------|-------------------|-----------------------------------|
| [📊 Resource Monitoring](#resource-monitoring) | [🛡️ Security](#security-considerations) | [🔧 Troubleshooting](#troubleshooting) | [📦 Requirements](#requirements) | [📚 Contributing](#contributing) |

## Overview

Green-Boy is a Telegram bot that makes SLURM cluster monitoring and job management easy and accessible from your mobile device or desktop. Monitor your jobs, receive notifications when they complete, check resource usage, and manage your workload - all through a simple chat interface.

⚠️ **IMPORTANT DISCLAIMER**

**USE AT YOUR OWN RISK**

This bot can perform destructive operations on your SLURM cluster, including:
- **Canceling running jobs** (potentially causing data loss)
- **Submitting new jobs** (consuming cluster resources)
- **Accessing job information** (potential privacy implications)

**By using Green-Boy, you acknowledge that:**
- ❌ **The authors are NOT responsible** for any job failures, data loss, cluster disruptions, or other problems caused by using this bot
- 🔒 **You are solely responsible** for properly configuring authorization and securing access
- 🧪 **You should test thoroughly** in a safe environment before using in production
- 📋 **You must comply** with your organization's policies and cluster usage guidelines
- 🔐 **You assume full liability** for all actions performed through this bot

**Recommendations:**
- Always test with non-critical jobs first
- Use the authorization system to restrict access
- Monitor bot activity and logs regularly
- Have backups of important data

[Back to Navigation](#navigation)

---

## Features

🚀 **Job Management**
- List your jobs with customizable filters
- Cancel running jobs
- Submit new job scripts
- Get detailed job information including resource usage
- Monitor jobs for completion notifications

📊 **Resource Monitoring**
- Real-time CPU and memory usage for running jobs
- Historical resource usage for completed jobs
- Per-task resource breakdown
- Energy consumption tracking
- Exit status tracking and interpretation

🖥️ **Cluster Information**
- Overall cluster status and availability
- Partition information
- Node status
- Custom SLURM command execution

🔐 **Security**
- User authorization system
- Configurable access control
- User-specific resources to prevent conflicts

[Back to Navigation](#navigation)

## Installation

### Prerequisites

- Python 3.7+
- Access to a SLURM cluster with command-line tools (`squeue`, `scontrol`, `sstat`, `sacct`, etc.)
- A Telegram bot token (instructions below)

### Creating a Telegram Bot

1. **Open Telegram** and search for [@BotFather](https://t.me/botfather)
2. **Start a chat** with BotFather and send the command `/newbot`
3. **Follow the instructions** to name your bot:
   - First provide a display name (e.g., "My SLURM Manager")
   - Then provide a username that must end with "bot" (e.g., "my_slurm_manager_bot")
4. **Save the API token** BotFather gives you - it looks like `123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ`
5. **Optional:** Customize your bot with `/setdescription`, `/setabouttext`, and `/setuserpic` commands

### Finding Your Telegram User ID

To restrict bot access to authorized users, you'll need your Telegram user ID:

1. **Start a chat** with [@userinfobot](https://t.me/userinfobot) on Telegram
2. **The bot will reply** with your information, including your User ID (a number like `123456789`)
3. **Collect User IDs** from everyone who should have access to your bot
4. **Use these IDs** in the `GREENBOY_AUTH_USERS` environment variable (see below)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/adamlaho/green-boy.git
   cd green-boy
   ```

2. **Install required Python packages**
   ```bash
   pip install -r requirements.txt
   ```
   
   *If the above doesn't work, try:*
   ```bash
   python3 -m pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   export GREENBOY_AUTH_USERS="123456789,987654321"  # Comma-separated user IDs
   ```

4. **Run the bot**
   ```bash
   python3 green-boy.py
   ```

5. **Start using your bot**
   - Open Telegram and search for your bot's username
   - Start a conversation and use `/start` to verify it's working

[Back to Navigation](#navigation)

## Usage

### Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message and bot introduction | `/start` |
| `/help` | Show all available commands | `/help` |
| `/squeue [FLAGS]` | List your jobs (defaults to running jobs) | `/squeue -p gpu -t PD` |
| `/cancel <JOBID>` | Cancel a specific job | `/cancel 12345678` |
| `/jobinfo <JOBID>` | Show detailed job info with resource usage | `/jobinfo 12345678` |
| `/status` | Show overall cluster status | `/status` |
| `/submit <script>` | Submit a job script | `/submit /path/to/job.sh` |
| `/monitor <JOBID>` | Monitor a job for completion notifications | `/monitor 12345678` |
| `/unmonitor <JOBID>` | Stop monitoring a job | `/unmonitor 12345678` |
| `/monitorlist` | List all jobs being monitored | `/monitorlist` |
| `/custom <command> [args]` | Run a custom SLURM command | `/custom sacct --jobs=12345 --format=JobID,State,ExitCode -P` |
| `/shutdown` | 🔴 Safely shutdown the bot (authorized users only) | `/shutdown` |

### Interactive Features

The bot includes interactive buttons for common actions:

- **Queue Filters**: Quick buttons to filter jobs (All, Running, Pending, GPU)
- **Job Actions**: Cancel jobs directly from job information
- **Resource Details**: View detailed CPU and memory usage for running jobs
- **Job Monitoring**: Monitor jobs for completion and get notifications
- **Bot Management**: Shutdown button for authorized users

### Examples

**List all your jobs:**
```
/squeue
```

**List pending jobs:**
```
/squeue -t PD
```

**List jobs on GPU partition:**
```
/squeue -p gpu
```

**Get detailed job information:**
```
/jobinfo 12345678
```

**Cancel a job:**
```
/cancel 12345678
```

**Submit a job script:**
```
/submit /home/user/my_job.sh
```

**Monitor a job for completion:**
```
/monitor 12345678
```

**List all jobs being monitored:**
```
/monitorlist
```

**Run a custom SLURM command to check exit codes:**
```
/custom sacct --jobs=12345678 --format=JobID,State,ExitCode,Start,End,Elapsed -P
```

**Shutdown the bot remotely:**
```
/shutdown
```

[Back to Navigation](#navigation)

## Proper Shutdown Procedures

Green-Boy offers multiple ways to properly shutdown the bot. It's important to use these methods rather than simply killing the process, as they ensure proper resource cleanup.

### Method 1: Using the Shutdown Command

The safest way to shutdown Green-Boy is using the built-in command:
```
/shutdown
```
This command:
- Only works for authorized users
- Provides a confirmation button
- Properly releases all resources
- Clears webhooks and connections

### Method 2: Using Ctrl+C in Terminal

If you're running the bot in a terminal, press `Ctrl+C` to initiate a graceful shutdown.

### Method 3: Emergency Shutdown Script

For cases where the bot is unresponsive or the above methods don't work, use the emergency shutdown script:

```bash
# Create the emergency shutdown script
chmod +x emergency_shutdown.sh
./emergency_shutdown.sh
```

This script:
- Forcefully terminates all Green-Boy processes for your user
- Cleans up lock files and resources
- Verifies all processes are properly terminated

### Method 4: Manual Process Killing

As a last resort, you can manually find and kill the process:
```bash
# Find the process ID
ps aux | grep "green-boy.py" | grep -v grep

# Kill it forcefully
kill -9 PROCESS_ID
```

### ⚠️ Important: After Shutdown

After shutting down the bot, ensure these resources are cleaned up:
1. No Green-Boy processes are still running
2. The lock file is removed (`/tmp/greenboy-USERNAME.lock`)
3. The socket port is freed

[Back to Navigation](#navigation)

## Resource Monitoring

Green-Boy provides comprehensive resource monitoring:

### For Running Jobs
- Real-time CPU usage (average and per-task)
- Memory usage (RSS and virtual memory)
- CPU frequency
- Energy consumption
- Per-task breakdown

### For Completed Jobs
- Historical CPU usage
- Peak memory usage
- Total CPU time
- Exit codes with interpretation (success/failure)
- Job duration and resource consumption

### Job Completion Monitoring
- Automatic notifications when jobs finish
- Exit status and duration reporting
- Resource usage summary
- Direct links to detailed job information

## Deployment

### Using Screen or Tmux

For keeping the bot running after you log out:

```bash
# Using screen
screen -S green-boy
python3 green-boy.py
# Ctrl+A, D to detach

# Using tmux
tmux new-session -d -s green-boy 'python3 green-boy.py'
```

### Using Aliases (Quick Commands)

You can create convenient aliases for starting and stopping the bot:

```bash
# Add these to your ~/.bashrc or ~/.zshrc
alias green-boy-start='nohup nice -n 19 python3 /path/to/green-boy/green-boy.py &'
alias green-boy-kill='pkill -f green-boy.py'
```

Then use them like:
```bash
# Start the bot (low priority, background)
green-boy-start

# Stop the bot
green-boy-kill

# Check if it's running
ps aux | grep green-boy.py
```

**Note:** Update the path `/path/to/green-boy/green-boy.py` to match your installation directory.

## Security Considerations

⚠️ **Critical Security Notice:**
- **Always configure authorization**: Set `GREENBOY_AUTH_USERS` to restrict access
- **Monitor bot usage**: Review logs regularly for unauthorized access
- **Secure your token**: Keep your `TELEGRAM_BOT_TOKEN` secret
- **Test permissions**: Ensure bot users only have appropriate SLURM access
- **Network security**: Consider firewall restrictions and VPN access
- **Custom command limitations**: Only whitelisted SLURM commands are allowed via `/custom`

Additional security measures:
- **Permissions**: The bot runs with the permissions of the user executing it
- **Logs**: Monitor logs for unauthorized access attempts
- **Cluster coordination**: Inform cluster administrators about bot deployment

## Troubleshooting

### API Conflict Issues

If you encounter persistent Telegram API conflicts (error message: "Conflict: terminated by other getUpdates request"), follow these steps:

1. **First, try the aggressive reset script:**
   ```bash
   chmod +x telegram_api_reset.sh
   ./telegram_api_reset.sh
   ```
   This script performs a comprehensive reset of API connections and waits for them to fully settle.

2. **If conflicts persist, create a new bot token:**
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Use the `/newbot` command to create a new bot
   - Update your environment variable with the new token:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_new_token_here"
   ```
   - Restart the bot with the new token

3. **Important:** When the error "Conflict: terminated by other getUpdates request" persists despite cleanup attempts, it usually indicates the token has issues at Telegram's server side and creating a new bot is the most reliable solution.

### Bot Cleanup Tool

If your bot isn't responding or you're getting webhook conflicts, use the included cleanup script:

```bash
python3 cleanup_bot.py
```

**When to use `cleanup_bot.py`:**
- 🔄 Bot was previously running in webhook mode
- 🚫 Bot not responding to commands
- ⚠️ Getting "webhook already set" errors
- 🔄 Switching from webhook to polling mode
- 🧹 Bot behaving unexpectedly

**What it does:**
- Deletes any existing webhooks
- Clears pending message updates
- Verifies bot connection
- Resets the bot to a clean state

**Usage:**
1. Stop your current bot instance
2. Run the cleanup script
3. Wait 10-15 seconds
4. Start your bot normally

### Process Management

Check for existing bot processes:
```bash
python3 check_processes.py
```

### Common Issues

**Bot doesn't respond:**
- Check if `TELEGRAM_BOT_TOKEN` is set correctly
- Verify bot token with BotFather
- Check network connectivity

**SLURM commands fail:**
- Ensure SLURM tools are installed and accessible
- Check if the user has appropriate SLURM permissions
- Verify SLURM cluster is accessible

**Authorization errors:**
- Check if your user ID is in `GREENBOY_AUTH_USERS`
- Get your user ID from [@userinfobot](https://t.me/userinfobot)

**Webhook conflicts:**
- Run `python3 cleanup_bot.py`
- Wait before restarting the bot
- Check for multiple bot instances

**Job monitoring issues:**
- Check if the monitored jobs file (`monitored_jobs.json`) is writable
- Verify the bot has permissions to read job status
- Ensure the bot is running continuously without interruptions

**Shutdown button not working:**
- If the bot is unresponsive and the shutdown button doesn't work
- Use the emergency shutdown script or manually kill the process
- If this occurs frequently, consider creating a new bot token

### Logging

The bot logs activities to stdout. To save logs:
```bash
python3 green-boy.py > green-boy.log 2>&1
```

## Requirements

- **Python**: 3.7+
- **Python packages**:
  - `python-telegram-bot`
  - `requests`
  - `psutil` (for process management)
- **System tools**:
  - `squeue`, `scontrol`, `sstat`, `sacct` (SLURM tools)
- **Permissions**:
  - Execute SLURM commands
  - Read job scripts for submission

## Contributing

Feel free to submit issues, feature requests, or pull requests. Some areas for improvement:

- Add more SLURM commands
- Enhanced resource visualization
- Job performance analytics
- Email notifications integration
- Web dashboard
- Enhanced security features
- Extended job monitoring capabilities

## License

This project is provided as-is under the MIT License for educational and research purposes. 

**DISCLAIMER: THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.**

Please ensure compliance with your organization's policies when using on shared systems.

## Changelog

### v1.3.2
- Added user-specific resource handling to prevent conflicts in shared environments
- Created emergency shutdown script for unresponsive bots
- Added aggressive API reset script for persistent Telegram conflicts
- Improved error handling and recovery for API issues
- Enhanced documentation for proper shutdown procedures

### v1.3.1
- Added exit status display for completed jobs
- Added custom command functionality with `/custom` command
- Enhanced job monitoring with improved notifications
- Added exit code interpretation (success/failure indicators)
- Added persistence for monitored jobs across bot restarts

### v1.2
- Added automatic job completion monitoring
- New commands:
  - `/monitor <jobid>` - Start monitoring a job
  - `/unmonitor <jobid>` - Stop monitoring a job
  - `/monitorlist` - Show all monitored jobs
- Background task checks job status every 60 seconds
- Sends notifications when jobs complete, including:
  - Final job state
  - Exit code with interpretation

### v1.1
- Added remote shutdown functionality
- Enhanced job cancellation with improved error handling
- Better conflict resolution and startup reliability
- Process management tools (cleanup_bot.py, check_processes.py)
- Improved security with triple authorization checks

### v1.0
- Initial release
- Basic SLURM job monitoring
- Resource usage tracking
- Interactive Telegram interface
- Authorization system

---

*Green-Boy - Making SLURM monitoring more accessible, one message at a time! 🌱*

**Remember: With great power comes great responsibility. Use Green-Boy wisely!** ⚡
