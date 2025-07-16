import os
import logging
import asyncio
import aiohttp
import json
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
from subprocess import Popen, PIPE
from datetime import datetime
from aiohttp import web

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
API_ID = int(os.getenv('API_ID', 26494161))
API_HASH = os.getenv('API_HASH', '55da841f877d16a3a806169f3c5153d3')
BOT_TOKEN = os.getenv('BOT_TOKEN', '7758524025:AAEVf_OePVQ-6hhM1GfvRlqX3QZIqDOivtw')
API_ENDPOINT = os.getenv('API_ENDPOINT', 'http://zozo-api.onrender.com/download?url=')
PORT = int(os.getenv('PORT', 8080))
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB

# Initialize Telegram client
bot = TelegramClient('terabox_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Start command handler
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    welcome_message = """
🚀 **Welcome to Terabox Downloader Bot** 🚀

Send me any Terabox link and I'll download and upload the file for you!

🔹 **Features:**
- Fast downloads using aria2c
- Progress tracking for both download and upload
- Thumbnail support
- Video streaming support

📌 **Note:** 
- Maximum file size: 2GB
- Only Terabox links are supported

Enjoy using the bot! 😊
"""
    await event.reply(welcome_message, parse_mode='md')

async def fetch_terabox_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_ENDPOINT}{url}") as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def download_with_progress(url, file_path, message, download_type="Downloading"):
    cmd = [
        'aria2c',
        '--max-connection-per-server=16',
        '--split=16',
        '--dir=/tmp',
        '--out=' + file_path,
        url
    ]
    
    process = Popen(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)
    
    last_update_time = 0
    while True:
        output = process.stderr.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            if 'DOWNLOAD' in output:
                try:
                    parts = output.split()
                    speed = parts[7]
                    percent = parts[1]
                    downloaded = parts[3]
                    total_size = parts[5]
                    
                    current_time = datetime.now().timestamp()
                    if current_time - last_update_time > 5:  # Update every 5 seconds
                        await message.edit(f"**{download_type} Progress**\n\n"
                                        f"**File:** `{file_path}`\n"
                                        f"**Progress:** `{percent}`\n"
                                        f"**Downloaded:** `{downloaded}` of `{total_size}`\n"
                                        f"**Speed:** `{speed}`")
                        last_update_time = current_time
                except Exception as e:
                    logger.error(f"Error parsing aria2c output: {e}")
    
    return process.poll() == 0

async def upload_with_progress(client, file_path, message, chat_id, thumb_path=None):
    last_update_time = 0
    file_size = os.path.getsize(file_path)
    uploaded = 0
    
    def progress_callback(current, total):
        nonlocal uploaded, last_update_time
        uploaded = current
        current_time = datetime.now().timestamp()
        if current_time - last_update_time > 5:  # Update every 5 seconds
            percent = (current / total) * 100
            speed = (current - uploaded) / (1024 * 1024 * 5)  # MB per 5 sec
            asyncio.create_task(
                message.edit(f"**Uploading Progress**\n\n"
                           f"**File:** `{file_path}`\n"
                           f"**Progress:** `{percent:.2f}%`\n"
                           f"**Uploaded:** `{current / (1024 * 1024):.2f}MB` of `{total / (1024 * 1024):.2f}MB`\n"
                           f"**Speed:** `{speed:.2f} MB/s`")
            )
            last_update_time = current_time
    
    try:
        attributes = []
        if file_path.lower().endswith(('.mp4', '.mkv', '.mov', '.avi')):
            # Get video duration and dimensions using ffmpeg
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration:stream=width,height', '-of',
                'json', file_path
            ]
            process = Popen(cmd, stdout=PIPE, stderr=PIPE)
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                info = json.loads(stdout)
                duration = int(float(info['format']['duration']))
                width = info['streams'][0]['width']
                height = info['streams'][0]['height']
                
                attributes = [
                    DocumentAttributeVideo(
                        duration=duration,
                        w=width,
                        h=height,
                        round_message=False,
                        supports_streaming=True
                    )
                ]
        
        # Generate thumbnail if not provided
        if thumb_path is None and file_path.lower().endswith(('.mp4', '.mkv', '.mov', '.avi')):
            thumb_path = f"/tmp/{os.path.basename(file_path)}.jpg"
            cmd = [
                'ffmpeg', '-i', file_path, '-ss', '00:00:01', '-vframes', '1',
                '-q:v', '2', thumb_path
            ]
            process = Popen(cmd, stdout=PIPE, stderr=PIPE)
            process.wait()
            if not os.path.exists(thumb_path):
                thumb_path = None
        
        await client.send_file(
            chat_id,
            file_path,
            thumb=thumb_path,
            attributes=attributes,
            progress_callback=progress_callback,
            caption=f"Uploaded by Terabox Bot"
        )
        
        return True
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return False
    finally:
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

@bot.on(events.NewMessage(pattern=r'https?://[^\s]+terabox[^\s]+'))
async def handle_terabox_link(event):
    url = event.text.strip()
    message = await event.reply("Processing your Terabox link...")
    
    try:
        # Fetch terabox data from API
        data = await fetch_terabox_data(url)
        if not data:
            await message.edit("Failed to fetch Terabox data. Please check the link and try again.")
            return
        
        file_name = data.get('name', 'terabox_file')
        download_url = data.get('download_link')
        thumbnail_url = data.get('thumbnail')
        
        if not download_url:
            await message.edit("No download link found in the response.")
            return
        
        # Download thumbnail if available
        thumb_path = None
        if thumbnail_url:
            thumb_path = f"/tmp/thumb_{os.path.basename(file_name)}.jpg"
            success = await download_with_progress(thumbnail_url, thumb_path, message, "Downloading Thumbnail")
            if not success:
                thumb_path = None
        
        # Download main file
        file_path = f"/tmp/{file_name}"
        await message.edit("Starting download...")
        success = await download_with_progress(download_url, file_path, message)
        
        if not success:
            await message.edit("Failed to download the file.")
            return
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            await message.edit(f"File is too large ({file_size / (1024 * 1024):.2f}MB). Max allowed size is {MAX_FILE_SIZE / (1024 * 1024):.2f}MB.")
            os.remove(file_path)
            return
        
        # Upload to Telegram
        await message.edit("Starting upload...")
        success = await upload_with_progress(bot, file_path, message, event.chat_id, thumb_path)
        
        if success:
            await message.edit("File successfully uploaded!")
        else:
            await message.edit("Failed to upload the file.")
        
    except Exception as e:
        logger.error(f"Error processing Terabox link: {e}")
        await message.edit(f"An error occurred: {str(e)}")
    finally:
        # Clean up
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        if 'thumb_path' in locals() and thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

async def health_check(request):
    return web.Response(text="Bot is running")

async def start_server():
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Server started on port {PORT}")

async def main():
    await asyncio.gather(
        bot.start(),
        start_server()
    )
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
