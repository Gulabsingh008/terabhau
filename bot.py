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

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

bot = Client(
    'terabox_bot',
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=16
)

loop = asyncio.get_event_loop()

def parse_size(size_str):
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    size, unit = re.match(r'([\d.]+)\s*([A-Za-z]+)', size_str).groups()
    return float(size) * units[unit.upper()]

def download_with_aria(url, filename):
    cmd = [
        'aria2c', '-x', '32', '-s', '32', '-k', '2M', '-j', '32',
        '-d', DOWNLOAD_DIR, '-o', filename,
        '--file-allocation=falloc', '--summary-interval=0', '--console-log-level=warn', url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return os.path.join(DOWNLOAD_DIR, filename), result.returncode == 0

def get_zozo_data(url):
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
    return jsonify({ 'status': 'active', 'service': 'Terabox Telegram Bot', 'creator': 'Zozo ️' })

@app.route('/stream/<path:url>')
def stream_video(url):
    url = unquote(url)
    try:
        cmd = ['ffmpeg', '-i', url, '-f', 'mp4', '-movflags', 'frag_keyframe+empty_moov', '-']
        return Response(
            subprocess.Popen(cmd, stdout=subprocess.PIPE).stdout,
            mimetype='video/mp4', direct_passthrough=True
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
        "- Supports videos up to 2GB\n"
        "- Fast downloads using multi-connection\n"
        "- Direct streaming option\n\n"
        "Created by Zozo ️"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.regex(r'https?://[^\s]+'))
async def handle_links(client: Client, message: Message):
    url = message.text.strip()
    msg = await message.reply_text("Fetching video info from Zozo API...")

    data = get_zozo_data(url)
    if not data:
        await msg.edit_text("❌ Failed to fetch video info. Please try again later.")
        return

    try:
        file_name = data['name']
        size_bytes = parse_size(data['size'])
        download_link = data['download_link']

        MAX_SIZE = 2 * 1024**3
        if size_bytes > MAX_SIZE:
            await msg.edit_text(f"❌ File too large ({data['size']}). Max supported size is 2GB.")
            return

        async def update_download_progress():
            for i in range(1, 21):
                progress_bar = "⬢" * i + "⬡" * (20 - i)
                await msg.edit_text(f"⬇️ Downloading: {file_name}\n{progress_bar}")
                await asyncio.sleep(1.5)

        asyncio.create_task(update_download_progress())

        def download_task():
            try:
                file_path, success = download_with_aria(download_link, file_name)
                if not success:
                    loop.call_soon_threadsafe(asyncio.create_task, msg.edit_text(f"❌ Download failed for {file_name}"))
                    return

                loop.call_soon_threadsafe(asyncio.create_task, msg.edit_text(f"✅ Download complete. Uploading: {file_name}\n⏳ Please wait..."))
                loop.call_soon_threadsafe(asyncio.create_task, send_video(message, file_path, file_name, msg))

            except Exception as e:
                logger.error(f'Download error: {str(e)}')
                loop.call_soon_threadsafe(asyncio.create_task, msg.edit_text(f"❌ Download error: {str(e)}"))

        threading.Thread(target=download_task).start()

    except Exception as e:
        logger.error(f'Processing error: {str(e)}')
        await msg.edit_text(f"❌ Error: {str(e)}")

async def send_video(message: Message, file_path: str, file_name: str, msg: Message):
    try:
        await message.reply_video(
            video=file_path,
            caption=f"✅ {file_name}\n\nPowered by @{bot.me.username}",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(msg, file_name),
            chunk_size=5 * 1024 * 1024,
            workers=4
        )
        await msg.delete()
    except FilePartMissing as e:
        await msg.edit_text(f"❌ Upload failed: {str(e)}")
    except Exception as e:
        await msg.edit_text(f"❌ Upload error: {str(e)}")
    finally:
        try:
            os.remove(file_path)
        except:
            pass

async def progress_callback(current, total, msg: Message, file_name: str):
    percent = current * 100 / total
    progress_bar = "⬢" * int(percent / 5) + "⬡" * (20 - int(percent / 5))
    try:
        await msg.edit_text(
            f"Uploading: {file_name}\n{progress_bar}\n{human_readable_size(current)} / {human_readable_size(total)} ({percent:.1f}%)"
        )
    except:
        pass

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
