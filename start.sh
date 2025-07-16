#!/bin/bash

echo "🔄 Starting Aria2c in daemon mode with high-speed config..."

aria2c \
  --enable-rpc \
  --rpc-listen-all=true \
  --rpc-allow-origin-all \
  --rpc-listen-port=6800 \
  --max-connection-per-server=32 \
  --split=32 \
  --min-split-size=2M \
  --file-allocation=falloc \
  --continue=true \
  --max-concurrent-downloads=5 \
  --daemon=true

echo "✅ Aria2c daemon started."

# Wait for a moment to ensure Aria2 is ready
sleep 2

echo "🚀 Starting Telegram Bot..."
python bot.py
