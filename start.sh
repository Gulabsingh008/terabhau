#!/bin/bash

# Start aria2c daemon
aria2c --enable-rpc --rpc-listen-all=true --rpc-allow-origin-all --rpc-listen-port=6800 --daemon=true

# Start the bot
python bot.py
