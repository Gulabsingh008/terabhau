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

bot = Client(
    'terabox_bot',
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=16,
    in_memory=True
)

def parse_size(size_str):
    """Convert size string (like '171.07 MB') to bytes"""
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    size, unit = re.match(r'([\d.]+)\s*([A-Za-z]+)', size_str).groups()
    return float(size) * units[unit.upper()]

def download_with_aria(url, filename):
    """Download file using aria2c with optimized settings"""
    try:
        cmd = [
            'aria2c',
            '--summary-interval=0',
            '--console-log-level=warn',
            '-x', '16',
            '-s', '16',
            '-j', '16',
            '-k', '1M',
            '--file-allocation=prealloc',
            '-d', DOWNLOAD_DIR,
            '-o', filename,
            url
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3600
        )
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        return file_path, result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error(f"Download timed out for {filename}")
        return None, False
    except Exception as e:
        logger.error(f"Download error for {filename}: {str(e)}")
        return None, False
    
def get_zozo_data(url):
    """Fetch video metadata from Zozo API"""
    try:
        api_url = f'https://zozo-api.onrender.com/download?url={url}'
        response = requests.get(api_url, timeout=45)
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
    help_text = (
        " **Terabox Video Downloader Bot** \n\n"
        "Send me a Terabox share link and I'll download the video for you!\n\n"
        "Features:\n"
        "- Fast downloads with multi-connection\n"
        "- Direct streaming available\n"
        "- Supports files up to 2GB\n\n"
        "Created by Zozo ️"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.regex(r'https?://[^\s]+'))
async def handle_links(client: Client, message: Message):
    url = message.text.strip()
    try:
        msg = await message.reply_text("Fetching video info from Zozo API...")
        
        # Get video metadata
        data = get_zozo_data(url)
        if not data:
            await msg.edit_text("❌ Failed to fetch video info. Please try again.")
            return
        
        file_name = data['name']
        size_bytes = parse_size(data['size'])
        download_link = data['download_link']
        
        # Check file size
        MAX_SIZE = 2 * 1024**3  # 2GB
        if size_bytes > MAX_SIZE:
            await msg.edit_text(
                f"❌ File too large ({data['size']}). Max size: 2GB"
            )
            return
        
        await msg.edit_text(
            f"Downloading: {file_name}\n"
            f"Size: {data['size']}\n"
            "⏳ This may take a while for large files..."
        )
        
        # Download file in background thread
        def download_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                file_path, success = download_with_aria(download_link, file_name)
                if not success or not file_path:
                    loop.run_until_complete(
                        msg.edit_text(f"❌ Download failed for {file_name}")
                    )
                    return
                
                loop.run_until_complete(
                    send_video(message, file_path, file_name)
                )
            except Exception as e:
                error_msg = f"❌ Download error: {str(e)}"
                logger.error(error_msg, exc_info=True)
                try:
                    loop.run_until_complete(
                        message.reply_text(error_msg)
                    )
                except:
                    pass
            finally:
                loop.close()
        
        threading.Thread(target=download_task, daemon=True).start()
        
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await handle_links(client, message)
    except Exception as e:
        logger.error(f"Link handling error: {str(e)}")
        await message.reply_text(f"❌ Processing error: {str(e)}")

async def send_video(message: Message, file_path: str, file_name: str):
    if not file_path or not os.path.exists(file_path):
        await message.reply_text(f"❌ File not found after download: {file_name}")
        return

    try:
        # Create upload status message
        progress_msg = await message.reply_text(
            f"📤 Uploading: {file_name}\n"
            "⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡⬡\n"
            "0.0% (0.00 MB / 0.00 MB)"
        )
        
        # Send video with progress tracking (removed unsupported parameters)
        await message.reply_video(
            video=file_path,
            caption=f"✅ {file_name}\n\nPowered by @{bot.me.username}",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(progress_msg, file_name)
        )
        
        # Update status to complete
        await progress_msg.edit_text(f"✅ Upload complete: {file_name}")
        
    except FilePartMissing as e:
        await progress_msg.edit_text(f"❌ Upload failed: {str(e)}")
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await send_video(message, file_path, file_name)
    except Exception as e:
        error_msg = f"❌ Upload error: {str(e)}"
        logger.error(error_msg)
        await progress_msg.edit_text(error_msg)
    finally:
        # Cleanup downloaded file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"File cleanup error: {str(e)}")

async def progress_callback(current: int, total: int, progress_msg: Message, file_name: str):
    """Update progress message during upload"""
    try:
        percent = (current / total) * 100
        progress_bar = "⬢" * int(percent / 5) + "⬡" * (20 - int(percent / 5))
        
        await progress_msg.edit_text(
            f"📤 Uploading: {file_name}\n"
            f"{progress_bar}\n"
            f"{human_readable_size(current)} / {human_readable_size(total)}"
            f" ({percent:.1f}%)"
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass  # Avoid failing entire upload due to progress update error

def human_readable_size(size: int) -> str:
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

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
