# ✅ Updated start.sh
# Note: aria2c has max limit of 16 connections per server. Your old value 32 was invalid.

#!/bin/bash

echo "🔄 Starting Aria2c in daemon mode with safe config..."

aria2c \
  --enable-rpc \
  --rpc-listen-all=true \
  --rpc-allow-origin-all \
  --rpc-listen-port=6800 \
  --max-connection-per-server=16 \
  --split=16 \
  --min-split-size=2M \
  --file-allocation=falloc \
  --continue=true \
  --max-concurrent-downloads=5 \
  --daemon=true

echo "✅ Aria2c daemon started."

# Wait to ensure aria2 is ready
sleep 2

echo "🚀 Starting Telegram Bot..."
python bot.py
