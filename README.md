![AMLP Logo](green_boy_logo.png)

## ⚠️ **IMPORTANT DISCLAIMER**

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
- Coordinate with your cluster administrators

---

## Features

🚀 **Job Management**
- List your jobs with customizable filters
- Cancel running jobs
- Submit new job scripts
- Get detailed job information including resource usage

📊 **Resource Monitoring**
- Real-time CPU and memory usage for running jobs
- Historical resource usage for completed jobs
- Per-task resource breakdown
- Energy consumption tracking

🖥️ **Cluster Information**
- Overall cluster status and availability
- Partition information
- Node status

🔐 **Security**
- User authorization system
- Configurable access control

## Installation

### Prerequisites

- Python 3.7+
- Access to a SLURM cluster with command-line tools (`squeue`, `scontrol`, `sstat`, `sacct`, etc.)
- A Telegram bot token (get one from [@BotFather](https://t.me/botfather))

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

3. **Create a Telegram bot**
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Use `/newbot` command and follow instructions
   - Save the bot token

4. **Configure environment variables**
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   export GREENBOY_AUTH_USERS="123456789,987654321"  # Optional: comma-separated user IDs
   ```

5. **Run the bot**
   ```bash
   python3 green-boy.py
   ```

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from BotFather | ✅ Yes | - |
| `GREENBOY_AUTH_USERS` | Comma-separated list of authorized Telegram user IDs | ❌ No | All users allowed |

### Getting Your Telegram User ID

To find your Telegram user ID:
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy the numerical ID
3. Add it to `GREENBOY_AUTH_USERS`

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
| `/shutdown` | 🔴 Safely shutdown the bot (authorized users only) | `/shutdown` |

### Interactive Features

The bot includes interactive buttons for common actions:

- **Queue Filters**: Quick buttons to filter jobs (All, Running, Pending, GPU)
- **Job Actions**: Cancel jobs directly from job information
- **Resource Details**: View detailed CPU and memory usage for running jobs
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

**Shutdown the bot remotely:**
```
/shutdown
```

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
- Exit codes and job state

## Deployment

### Using Screen or Tmux

```bash
# Using screen
screen -S green-boy
python3 green-boy.py
# Ctrl+A, D to detach

# Using tmux
tmux new-session -d -s green-boy 'python3 green-boy.py'
```

### Using Aliases (Quick Commands)

You can also create convenient aliases for starting and stopping the bot:

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

Additional security measures:
- **Permissions**: The bot runs with the permissions of the user executing it
- **Logs**: Monitor logs for unauthorized access attempts
- **Cluster coordination**: Inform cluster administrators about bot deployment

## Troubleshooting

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

## License

This project is provided as-is under the MIT License for educational and research purposes. 

**DISCLAIMER: THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.**

Please ensure compliance with your organization's policies when using on shared systems.

## Changelog

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
