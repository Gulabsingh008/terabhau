import os
import re
import json
import requests
import logging
import threading
import subprocess
import asyncio
from flask import Flask, Response, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FilePartMissing
from urllib.parse import unquote

# Initialize Flask app
app = Flask(__name__)
PORT = 8080

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Telegram bot configuration
API_ID = os.environ.get('API_ID', '26494161')
API_HASH = os.environ.get('API_HASH', '55da841f877d16a3a806169f3c5153d3')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7758524025:AAEVf_OePVQ-6hhM1GfvRlqX3QZIqDOivtw')
DOWNLOAD_DIR = 'downloads'
TEMP_DIR = 'temp'

# Create directories if not exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize Pyrogram client
bot = Client(
    'terabox_bot',
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=8  # Increased for concurrency
)

def parse_size(size_str):
    """Convert size string (like '171.07 MB') to bytes"""
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    size, unit = re.match(r'([\d.]+)\s*([A-Za-z]+)', size_str).groups()
    return float(size) * units[unit.upper()]

def download_with_aria(url, filename):
    """Download file using aria2c with multiple connections"""
    cmd = [
        'aria2c',
        '-x', '32',  # Use 32 connections for faster download
        '-s', '32',
        '-d', DOWNLOAD_DIR,
        '-o', filename,
        '--file-allocation=none',
        '--summary-interval=0',
        '--console-log-level=warn',
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return os.path.join(DOWNLOAD_DIR, filename), result.returncode == 0

def get_zozo_data(url):
    """Fetch video metadata from Zozo API"""
    try:
        api_url = f'https://zozo-api.onrender.com/download?url={url}'
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f'Zozo API error: {str(e)}')
        return None

@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        'status': 'active',
        'service': 'Terabox Telegram Bot',
        'creator': 'Zozo ️'
    })

@app.route('/stream/<path:url>')
def stream_video(url):
    """Video streaming endpoint using ffmpeg"""
    url = unquote(url)
    try:
        cmd = [
            'ffmpeg',
            '-i', url,
            '-f', 'mp4',
            '-movflags', 'frag_keyframe+empty_moov',
            '-'
        ]
        return Response(
            subprocess.Popen(cmd, stdout=subprocess.PIPE).stdout,
            mimetype='video/mp4',
            direct_passthrough=True
        )
    except Exception as e:
        logger.error(f'Stream error: {str(e)}')
        return jsonify({'error': 'Stream failed'}), 500

@bot.on_message(filters.command(['start', 'help']))
async def start_command(client: Client, message: Message):
    """Handle /start and /help commands"""
    help_text = (
        " **Terabox Video Downloader Bot** \n\n"
        "Send me a Terabox share link and I'll download the video for you!\n\n"
        "Features:\n"
        "- Supports videos up to 2GB\n"
        "- Fast downloads using multi-connection\n"
        "- Di option\n\n"
        "Created by Zozo ️"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.regex(r'https?://[^\s]+'))
async def handle_links(client: Client, message: Message):
    """Process Terabox links"""
    url = message.text.strip()
    msg = await message.reply_text(" Fetching video info from Zozo API...")
    
    # Get video metadata
    data = get_zozo_data(url)
    if not data:
        await msg.edit_text("❌ Failed to fetch video info. Please try again later.")
        return
    
    try:
        file_name = data['name']
        size_bytes = parse_size(data['size'])
        download_link = data['download_link']
        
        # Check file size
        MAX_SIZE = 2 * 1024**3  # 2GB
        if size_bytes > MAX_SIZE:
            await msg.edit_text(
                f"❌ File too large ({data['size']}). "
                f"Max supported size is 2GB."
            )
            return
        
        # Prepare download
        await msg.edit_text(
            f"📥 Downloading: {file_name}\n"
            f"📏 Size: {data['size']}\n"
            "⏳ This may take a while for large files..."
        )
        
        # Download file in background thread
        def download_task():
            try:
                file_path, success = download_with_aria(download_link, file_name)
                if not success:
                    bot.loop.create_task(
                        msg.edit_text(f"❌ Download failed for {file_name}")
                    )
                    return
                
                # Send video to user
                bot.loop.create_task(
                    send_video(message, file_path, file_name)
                )
            except Exception as e:
                logger.error(f'Download error: {str(e)}')
                bot.loop.create_task(
                    msg.edit_text(f"❌ Download error: {str(e)}")
                )
        
        threading.Thread(target=download_task).start()
        
    except Exception as e:
        logger.error(f'Processing error: {str(e)}')
        await msg.edit_text(f"❌ Error: {str(e)}")

async def send_video(message: Message, file_path: str, file_name: str):
    """Send video to user with progress updates"""
    msg = await message.reply_text(
        f"📤 Uploading: {file_name}\n"
        "⏳ Please wait..."
    )
    
    try:
        # Send video with progress
        await message.reply_video(
            video=file_path,
            caption=f"✅ {file_name}\n\nPowered by @{bot.me.username}",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(msg, file_name)
        )
        await msg.delete()
    except FilePartMissing as e:
        await msg.edit_text(f"❌ Upload failed: {str(e)}")
    except Exception as e:
        await msg.edit_text(f"❌ Upload error: {str(e)}")
    finally:
        # Cleanup downloaded file
        try:
            os.remove(file_path)
        except:
            pass

async def progress_callback(current, total, msg: Message, file_name: str):
    """Update progress message during upload"""
    percent = current * 100 / total
    progress_bar = "⬢" * int(percent / 5) + "⬡" * (20 - int(percent / 5))
    try:
        await msg.edit_text(
            f"📤 Uploading: {file_name}\n"
            f"{progress_bar}\n"
            f"{human_readable_size(current)} / {human_readable_size(total)}"
            f" ({percent:.1f}%)"
        )
    except:
        pass

def human_readable_size(size):
    """Convert bytes to human-readable format"""
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"

def run_flask():
    """Run Flask server in separate thread"""
    app.run(host='0.0.0.0', port=PORT, threaded=True)

if __name__ == '__main__':
    # Start Flask server in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start Telegram bot
    logger.info("Starting Telegram bot...")
    bot.run()
