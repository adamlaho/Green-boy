# Green-Boy 🤖

A lightweight Telegram bot for SLURM job monitoring with enhanced resource usage monitoring capabilities.

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

1. **Clone or download the script**
   ```bash
   curl -O https://your-server/green-boy.py
   chmod +x green-boy.py
   ```

2. **Install required Python packages**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create a Telegram bot**
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Use `/newbot` command and follow instructions
   - Save the bot token

4. **Configure environment variables (in your .bashrc)**
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

### Interactive Features

The bot includes interactive buttons for common actions:

- **Queue Filters**: Quick buttons to filter jobs (All, Running, Pending, GPU)
- **Job Actions**: Cancel jobs directly from job information
- **Resource Details**: View detailed CPU and memory usage for running jobs

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

### As a Service (systemd)

Create a service file `/etc/systemd/system/green-boy.service`:

```ini
[Unit]
Description=Green-Boy SLURM Telegram Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/green-boy
Environment=TELEGRAM_BOT_TOKEN=your_token_here
Environment=GREENBOY_AUTH_USERS=123456789,987654321
ExecStart=/usr/bin/python3 /path/to/green-boy.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl enable green-boy.service
sudo systemctl start green-boy.service
```

### Using Screen or Tmux

```bash
# Using screen
screen -S green-boy
python3 green-boy.py
# Ctrl+A, D to detach

# Using tmux
tmux new-session -d -s green-boy 'python3 green-boy.py'
```

## Security Considerations

- **Authorization**: Use `GREENBOY_AUTH_USERS` to restrict access to specific users
- **Permissions**: The bot runs with the permissions of the user executing it
- **Network**: Consider running on a secure network or using VPN
- **Logs**: Monitor logs for unauthorized access attempts

## Troubleshooting

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

## License

This project is provided as-is for educational and research purposes. Please ensure compliance with your organization's policies when using on shared systems.

## Changelog

### v1.0
- Initial release
- Basic SLURM job monitoring
- Resource usage tracking
- Interactive Telegram interface
- Authorization system

---

*Green-Boy - Making SLURM monitoring more accessible, one message at a time! 🌱*
