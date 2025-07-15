import os
import re
import json
import requests
import logging
import threading
import asyncio
import aria2p  # For high-speed downloads
import ffmpeg  # For streaming
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
API_ID = os.environ.get('API_ID', '12345678')
API_HASH = os.environ.get('API_HASH', 'abcdef1234567890abcdef1234567890')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ')
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

# Initialize aria2p (connects to aria2c daemon started in start.sh)
aria2 = aria2p.API(
    aria2p.Client(
        host="http://localhost",
        port=6800
    )
)

def parse_size(size_str):
    """Convert size string (like '171.07 MB') to bytes"""
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    size, unit = re.match(r'([\d.]+)\s*([A-Za-z]+)', size_str).groups()
    return float(size) * units[unit.upper()]

async def download_with_aria2p(url, filename):
    """Download file using aria2p with high-speed settings"""
    try:
        options = {
            "max-connection-per-server": "32",  # High connections for speed
            "split": "32",  # Parallel segments
            "min-split-size": "2M",  # Larger segments
            "dir": DOWNLOAD_DIR,
            "out": filename,
            "file-allocation": "falloc"  # Faster allocation
        }
        download = aria2.add_urid(url, options=options)
        while not download.is_complete:
            await asyncio.sleep(1)  # Async wait for completion
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        return file_path, download.is_complete
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return None, False

def get_zozo_data(url):
    """Fetch video metadata from Zozo API"""
    try:
        api_url = f'https://zozo-api.onrender.com/download?url={url}'
        response = requests.get(api_url, timeout=30)  # Increased timeout
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
    """Video streaming endpoint using ffmpeg-python"""
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
    """Handle /start and /help commands"""
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
        stream_link = data['stream_link']
        
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
            f" Downloading: {file_name}\n"
            f" Size: {data['size']}\n"
            f"⏳ This may take a while for large files..."
        )
        
        # Download file in background thread
        def download_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                file_path, success = loop.run_until_complete(download_with_aria2p(download_link, file_name))
                if not success:
                    loop.run_until_complete(msg.edit_text(f"❌ Download failed for {file_name}"))
                    return
                
                loop.run_until_complete(send_video(message, file_path, file_name))
            except Exception as e:
                logger.error(f'Download error: {str(e)}')
                loop.run_until_complete(msg.edit_text(f"❌ Download error: {str(e)}"))
            finally:
                loop.close()
        
        threading.Thread(target=download_task).start()
        
    except Exception as e:
        logger.error(f'Processing error: {str(e)}')
        await msg.edit_text(f"❌ Error: {str(e)}")

async def send_video(message: Message, file_path: str, file_name: str):
    """Send video to user with progress updates"""
    msg = await message.reply_text(
        f" Uploading: {file_name}\n"
        "⏳ Please wait..."
    )
    
    try:
        # Send video with progress (using pyrogram>=2.0.0 features for speed)
        await message.reply_video(
            video=file_path,
            caption=f"✅ {file_name}\n\nPowered by @{bot.me.username}",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(msg, file_name),
            chunk_size=2 * 1024 * 1024,  # 2MB chunks for faster upload
            workers=8  # Parallel threads for speed
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
            f" Uploading: {file_name}\n"
            f"{progress_bar}\n"
            f" {human_readable_size(current)} / {human_readable_size(total)}"
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
