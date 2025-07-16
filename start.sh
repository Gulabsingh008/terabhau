#!/bin/bash

# Start aria2c daemon
echo "🔄 Starting Aria2c..."
aria2c \
  --enable-rpc \
  --rpc-listen-all \
  --rpc-allow-origin-all \
  --rpc-listen-port=6800 \
  --max-connection-per-server=16 \
  --split=16 \
  --min-split-size=2M \
  --file-allocation=falloc \
  --continue=true \
  --max-concurrent-downloads=5 \
  --daemon=true

# Wait for aria2c to be ready
echo "⏳ Waiting for Aria2c RPC..."
while ! aria2p --port 6800 stats >/dev/null 2>&1; do
  sleep 1
done

# Start the bot
echo "🚀 Starting Telegram Bot..."
python bot.py
