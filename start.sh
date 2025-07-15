#!/bin/bash

# Apply file descriptor limits
ulimit -n 100000

# Apply TCP tuning (if supported)
sysctl -p /etc/sysctl.conf

# Run the bot
python bot.py
