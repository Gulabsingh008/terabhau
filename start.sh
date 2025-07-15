#!/bin/bash

# Set open file limit (may not fully work on Render, but we try)
ulimit -n 100000

# Optional: print limits for logging/debugging
echo "Open file limit: $(ulimit -n)"
echo "Running bot..."

# Start your bot
python bot.py
