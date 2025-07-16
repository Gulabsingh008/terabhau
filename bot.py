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
    workers=8
)

# ✅ Fixed: added `client=` keyword
aria2 = aria2p.API(
    client=aria2p.Client(
        host="http://localhost",
        port=6800,
        secret=""
    )
)

def parse_size(size_str):
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    size, unit = re.match(r'([\d.]+)\s*([A-Za-z]+)', size_str).groups()
    return float(size) * units[unit.upper()]

def download_with_aria2p(url, filename):
    try:
        options = {
            "max-connection-per-server": "16",  # Safe range (1-16)
            "split": "16",
            "min-split-size": "2M",
            "dir": DOWNLOAD_DIR,
            "out": filename,
            "file-allocation": "falloc"
        }
        downloads = aria2.add_uris([url], options=options)
        download = downloads[0]

        while not download.is_complete and not download.has_failed:
            time.sleep(1)
            download.update()

        file_path = os.path.join(DOWNLOAD_DIR, filename)
        return file_path, download.is_complete
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return None, False


def get_zozo_data(url):
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
        await async_edit_msg(msg, "❌ Failed to fetch video info. Please try again later.")
        return

    try:
        file_name = data['name']
        size_bytes = parse_size(data['size'])
        download_link = data['download_link']
        stream_link = data['stream_link']

        MAX_SIZE = 2 * 1024**3
        if size_bytes > MAX_SIZE:
            await async_edit_msg(msg, f"❌ File too large ({data['size']}). Max supported size is 2GB.")
            return

        await async_edit_msg(msg, f" Downloading: {file_name}\n Size: {data['size']}\n⏳ This may take a while...")

        def download_task(msg_obj, message_obj, download_link, file_name):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    download_with_aria2p(download_link, file_name),
                    bot.loop
                )
                file_path, success = future.result()

                if not success:
                    asyncio.run_coroutine_threadsafe(
                        async_edit_msg(msg_obj, f"❌ Download failed for {file_name}"),
                        bot.loop
                    ).result()
                    return

                asyncio.run_coroutine_threadsafe(
                    send_video(message_obj, file_path, file_name),
                    bot.loop
                ).result()
            except Exception as e:
                logger.error(f'Download error: {str(e)}')
                asyncio.run_coroutine_threadsafe(
                    async_edit_msg(msg_obj, f"❌ Download error: {str(e)}"),
                    bot.loop
                ).result()

        threading.Thread(
            target=download_task,
            args=(msg, message, download_link, file_name)
        ).start()

    except Exception as e:
        logger.error(f'Processing error: {str(e)}')
        await async_edit_msg(msg, f"❌ Error: {str(e)}")

async def async_edit_msg(msg: Message, text: str):
    try:
        if msg.text != text:
            await msg.edit_text(text)
    except FloodWait as fw:
        await asyncio.sleep(fw.value)
        await msg.edit_text(text)
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            logger.error(f"Message edit failed: {str(e)}")


async def send_video(message: Message, file_path: str, file_name: str):
    msg = await message.reply_text(
        f" Uploading: {file_name}\n"
        "⏳ Please wait..."
    )

    try:
        me = await bot.get_me()  # ✅ Fix: Fetch bot username dynamically
        await message.reply_video(
            video=file_path,
            caption=f"✅ {file_name}\n\nPowered by @{me.username}",
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(msg, file_name),
            chunk_size=2 * 1024 * 1024,
            workers=8
        )
        await msg.delete()
    except FilePartMissing as e:
        await async_edit_msg(msg, f"❌ Upload failed: {str(e)}")
    except Exception as e:
        await async_edit_msg(msg, f"❌ Upload error: {str(e)}")
    finally:
        try:
            os.remove(file_path)
        except:
            pass

async def progress_callback(current, total, msg: Message, file_name: str):
    percent = current * 100 / total
    progress_bar = "⬢" * int(percent / 5) + "⬡" * (20 - int(percent / 5))
    new_text = (
        f" Uploading: {file_name}\n"
        f"{progress_bar}\n"
        f" {human_readable_size(current)} / {human_readable_size(total)}"
        f" ({percent:.1f}%)"
    )
    try:
        if msg.text != new_text:
            await msg.edit_text(new_text)
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
