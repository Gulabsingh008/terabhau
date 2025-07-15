import os
import re
import json
import requests
import logging
import threading
import asyncio
import aria2p
import ffmpeg
import subprocess
from flask import Flask, Response, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message
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

# Create directories if not exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Start aria2c daemon before initializing Pyrogram
try:
    subprocess.Popen([
        "aria2c",
        "--enable-rpc",
        "--rpc-listen-all=true",
        "--rpc-allow-origin-all",
        "--rpc-listen-port=6800",
        "--daemon=true",
        "--file-allocation=falloc"
    ])
    logger.info("Started aria2c daemon")
except Exception as e:
    logger.error(f"Failed to start aria2c: {str(e)}")

# Initialize Pyrogram client
bot = Client(
    'terabox_bot',
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=8
)

# Initialize aria2p
aria2 = aria2p.API(
    aria2p.Client(
        host="http://localhost",
        port=6800,
        timeout=10
    )
)

def parse_size(size_str):
    """Convert size string to bytes"""
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    size, unit = re.match(r'([\d.]+)\s*([A-Za-z]+)', size_str).groups()
    return float(size) * units[unit.upper()]

def get_zozo_data(url):
    """Fetch video metadata from Zozo API"""
    try:
        api_url = f'https://zozo-api.onrender.com/download?url={url}'
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f'Zozo API error: {str(e)}')
        return None

@app.route('/')
def home():
    return jsonify({
        'status': 'active',
        'service': 'Terabox Telegram Bot',
        'creator': 'Zozo ️'
    })

@app.route('/stream/<path:url>')
def stream_video(url):
    url = unquote(url)
    try:
        process = (
            ffmpeg
            .input(url)
            .output('pipe:', format='mp4', movflags='frag_keyframe+empty_moov')
            .run_async(pipe_stdout=True)
        )
        return Response(process.stdout, mimetype='video/mp4')
    except Exception as e:
        logger.error(f'Stream error: {str(e)}')
        return jsonify({'error': 'Stream failed'}), 500

@bot.on_message(filters.command(['start', 'help']))
async def start_command(client: Client, message: Message):
    help_text = (
        " **Terabox Video Downloader Bot** \n\n"
        "Send me a Terabox share link and I'll download the video for you!\n\n"
        "Features:\n"
        "- Supports videos up to 2GB\n"
        "- Fast downloads using multi-connection\n"
        "- Direct streaming option\n\n"
        "Created by Zozo ️"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.regex(r'https?://[^\s]+'))
async def handle_links(client: Client, message: Message):
    url = message.text.strip()
    msg = await message.reply_text(" Fetching video info from Zozo API...")
    
    data = get_zozo_data(url)
    if not data:
        await msg.edit_text("❌ Failed to fetch video info. Please try again later.")
        return
    
    try:
        file_name = data['name']
        size_bytes = parse_size(data['size'])
        download_link = data['download_link']
        
        MAX_SIZE = 2 * 1024**3  # 2GB
        if size_bytes > MAX_SIZE:
            await msg.edit_text(
                f"❌ File too large ({data['size']}). "
                f"Max supported size is 2GB."
            )
            return
        
        await msg.edit_text(
            f"📥 Downloading: {file_name}\n"
            f"📏 Size: {data['size']}\n"
            "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜\n"
            "0.0% (0.00 MB / 0.00 MB)"
        )
        
        def download_task():
            try:
                # Use integer values for numerical options
                options = {
                    "max-connection-per-server": 32,  # Integer, not string
                    "split": 32,
                    "min-split-size": "2M",
                    "dir": DOWNLOAD_DIR,
                    "out": file_name,
                    "file-allocation": "falloc"
                }
                download = aria2.add_uris([download_link], options=options)
                
                last_progress = 0
                while not download.is_complete:
                    progress = download.progress
                    if progress == last_progress:
                        asyncio.run_coroutine_threadsafe(asyncio.sleep(1), bot.loop).result()
                        continue
                    last_progress = progress
                    
                    progress_bar = "🟩" * int(progress / 5) + "⬜" * (20 - int(progress / 5))
                    downloaded = human_readable_size(download.completed_length)
                    total = human_readable_size(download.total_length)
                    
                    text = (
                        f"📥 Downloading: {file_name}\n"
                        f"📏 Size: {data['size']}\n"
                        f"{progress_bar}\n"
                        f"{progress:.1f}% ({downloaded} / {total})"
                    )
                    asyncio.run_coroutine_threadsafe(
                        async_edit_msg(msg, text), 
                        bot.loop
                    ).result()
                    
                file_path = os.path.join(DOWNLOAD_DIR, file_name)
                asyncio.run_coroutine_threadsafe(
                    send_video(message, file_path, file_name), 
                    bot.loop
                ).result()
                
            except Exception as e:
                logger.error(f'Download error: {str(e)}')
                asyncio.run_coroutine_threadsafe(
                    async_edit_msg(msg, f"❌ Download error: {str(e)}"), 
                    bot.loop
                ).result()
        
        threading.Thread(target=download_task, daemon=True).start()
        
    except Exception as e:
        logger.error(f'Processing error: {str(e)}')
        await msg.edit_text(f"❌ Error: {str(e)}")

async def async_edit_msg(msg: Message, text: str):
    try:
        await msg.edit_text(text)
    except Exception as e:
        logger.error(f"Error editing message: {str(e)}")

async def send_video(message: Message, file_path: str, file_name: str):
    try:
        upload_msg = await message.reply_text(
            f"📤 Uploading: {file_name}\n"
            "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜\n"
            "0.0% (0.00 MB / 0.00 MB)"
        )
        
        await message.reply_video(
            video=file_path,
            caption=f"✅ {file_name}\n\nPowered by @{bot.me.username}",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(upload_msg, file_name),
            chunk_size=2 * 1024 * 1024,
            workers=8
        )
        await upload_msg.delete()
    except FilePartMissing as e:
        await upload_msg.edit_text(f"❌ Upload failed: {str(e)}")
    except Exception as e:
        await upload_msg.edit_text(f"❌ Upload error: {str(e)}")
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"File cleanup error: {str(e)}")

async def progress_callback(current, total, msg: Message, file_name: str):
    try:
        percent = current * 100 / total
        progress_bar = "🟩" * int(percent / 5) + "⬜" * (20 - int(percent / 5))
        downloaded = human_readable_size(current)
        total_size = human_readable_size(total)
        
        if int(percent) != int(progress_callback.last_percent.get(file_name, -1)):
            progress_callback.last_percent[file_name] = int(percent)
            await msg.edit_text(
                f"📤 Uploading: {file_name}\n"
                f"{progress_bar}\n"
                f"{percent:.1f}% ({downloaded} / {total_size})"
            )
    except Exception as e:
        logger.error(f"Progress update error: {str(e)}")

# Initialize last percent tracker
progress_callback.last_percent = {}

def human_readable_size(size):
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"

def run_flask():
    app.run(host='0.0.0.0', port=PORT, threaded=True)

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Telegram bot...")
    bot.run()
