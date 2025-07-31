import os
import re
import json
import requests
import logging
import threading
import subprocess
import time
from flask import Flask, Response, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FilePartMissing, FloodWait
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
MAX_SIZE = 2 * 1024**3  # 2GB limit

# Create directories if not exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize Pyrogram client
bot = Client(
    'terabox_bot',
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=4
)

# Initialize user_data globally to avoid AttributeError
bot.user_data = {}

def download_with_aria(url, filename):
    """Download file using aria2c with multiple connections"""
    cmd = [
        'aria2c',
        '-x', '16',  # Use 16 connections
        '-s', '16',
        '-d', DOWNLOAD_DIR,
        '-o', filename,
        '--file-allocation=none',
        '--summary-interval=0',
        '--console-log-level=warn',
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    success = result.returncode == 0 and os.path.exists(file_path)
    return file_path, success

def get_zozo_data(url):
    """Fetch video metadata from your new API"""
    try:
        api_url = f'https://open-dragonfly-vonex-c2746ec1.koyeb.app/download?url={url}'  # Replace with your actual API URL
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('status') != "✅ Successfully":
            raise ValueError("API status not successful")
        return data
    except Exception as e:
        logger.error(f'API error: {str(e)}')
        return None

@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        'status': 'active',
        'service': 'Terabox Telegram Bot',
        'creator': 'TEAM - Zozo'
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
        "Send me a Terabox share link and I'll download or stream the video for you!\n\n"
        "Features:\n"
        "- Supports videos up to 2GB\n"
        "- Fast downloads using multi-connection\n"
        "- Direct streaming option\n"
        "- Fallback download if primary link fails\n\n"
        "Created by TEAM - Zozo"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.regex(r'https?://[^\s]+'))
async def handle_links(client: Client, message: Message):
    """Process Terabox links"""
    url = message.text.strip()
    msg = await message.reply_text(" Fetching video info from API...")
    
    # Get video metadata
    data = get_zozo_data(url)
    if not data:
        await msg.edit_text("❌ Failed to fetch video info. Please try again later.")
        return
    
    try:
        file_name = data['file_name']
        size_bytes = data['size_bytes']
        file_size_str = data['file_size']
        primary_link = data['download_link']
        fallback_link = data['link']
        stream_link = data['streaming_url']
        
        # Check file size
        if size_bytes > MAX_SIZE:
            await msg.edit_text(
                f"❌ File too large ({file_size_str}). "
                f"Max supported size is 2GB."
            )
            return
        
        # Provide options: Download or Stream
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Download", callback_data=f"download_{message.id}"),
            InlineKeyboardButton("Stream", callback_data=f"stream_{message.id}")
        ]])
        
        await msg.edit_text(
            f" File: {file_name}\n"
            f" Size: {file_size_str}\n"
            f"Choose an option:",
            reply_markup=keyboard
        )
        
        # Store data in the global dict
        bot.user_data[message.id] = {
            'file_name': file_name,
            'primary_link': primary_link,
            'fallback_link': fallback_link,
            'stream_link': stream_link,
            'size_bytes': size_bytes,
            'msg': msg
        }
        
    except Exception as e:
        logger.error(f'Processing error: {str(e)}')
        await msg.edit_text(f"❌ Error: {str(e)}")

@bot.on_callback_query()
async def handle_callback(client: Client, query):
    """Handle button callbacks for download/stream"""
    data = query.data
    message_id = int(data.split('_')[1])
    stored_data = bot.user_data.get(message_id)
    if not stored_data:
        await query.answer("Session expired. Please send the link again.")
        return
    
    msg = stored_data['msg']
    if data.startswith('download_'):
        await query.answer("Starting download...")
        await msg.edit_text(
            f" Downloading: {stored_data['file_name']}\n"
            f"⏳ This may take a while for large files..."
        )
        
        # Download in background
        threading.Thread(target=download_task, args=(query.message, stored_data)).start()
    
    elif data.startswith('stream_'):
        await query.answer("Generating stream link...")
        await msg.edit_text(
            f" Streaming URL for {stored_data['file_name']}:\n"
            f"{stored_data['stream_link']}\n\n"
            "Open in a video player that supports streaming."
        )

def download_task(message: Message, data: dict):
    """Background download task with fallback"""
    msg = data['msg']
    file_name = data['file_name']
    primary_link = data['primary_link']
    fallback_link = data['fallback_link']
    
    try:
        # Try primary link
        file_path, success = download_with_aria(primary_link, file_name)
        if not success:
            logger.info("Primary download failed, trying fallback...")
            file_path, success = download_with_aria(fallback_link, file_name)
        
        if not success:
            bot.loop.create_task(msg.edit_text(f"❌ Download failed for {file_name} (both links tried)."))
            return
        
        # Send video
        bot.loop.create_task(send_video(message, file_path, file_name))
    except Exception as e:
        logger.error(f'Download error: {str(e)}')
        bot.loop.create_task(msg.edit_text(f"❌ Download error: {str(e)}"))

async def send_video(message: Message, file_path: str, file_name: str):
    """Send video to user with progress updates"""
    msg = await message.reply_text(
        f" Uploading: {file_name}\n"
        "⏳ Please wait..."
    )
    
    try:
        start_time = time.time()
        await message.reply_video(
            video=file_path,
            caption=f"✅ {file_name}\n\nPowered by @{bot.me.username}",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(msg, file_name, start_time)
        )
        await msg.delete()
    except FilePartMissing as e:
        await msg.edit_text(f"❌ Upload failed: {str(e)}")
    except Exception as e:
        await msg.edit_text(f"❌ Upload error: {str(e)}")
    finally:
        # Cleanup
        try:
            os.remove(file_path)
        except:
            pass

async def progress_callback(current, total, msg: Message, file_name: str, start_time):
    """Update progress message during upload with ETA"""
    try:
        percent = current * 100 / total
        progress_bar = "⬢" * int(percent / 5) + "⬡" * (20 - int(percent / 5))
        speed = current / (time.time() - start_time) if time.time() - start_time > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        
        await msg.edit_text(
            f" Uploading: {file_name}\n"
            f"{progress_bar}\n"
            f" {human_readable_size(current)} / {human_readable_size(total)}"
            f" ({percent:.1f}%)\n"
            f" Speed: {human_readable_size(speed)}/s | ETA: {int(eta)}s"
        )
        await asyncio.sleep(10)  # Use async sleep to avoid blocking
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

def human_readable_size(size):
    """Convert bytes to human-readable format"""
    if size == 0:
        return "0B"
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
