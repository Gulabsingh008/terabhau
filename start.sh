#!/bin/bash

# Start aria2c daemon for aria2p (runs in background with RPC)
aria2c --daemon=true --enable-rpc --rpc-listen-all=true --rpc-allow-origin-all --rpc-listen-port=6800

# Apply file descriptor limits
ulimit -n 100000

# Apply TCP tuning (if supported)
sysctl -p /etc/sysctl.conf

# Run the bot
python bot.py
