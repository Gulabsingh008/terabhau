import os
import aiohttp
import asyncio
import subprocess
from os import environ
from pyrogram import Client, filters
from pyrogram.types import Message
from fastapi import FastAPI
import uvicorn
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
API_ID = int(environ.get('API_ID', '24519654'))
API_HASH = environ.get('API_HASH', '1ccea9c29a420df6a6622383fbd83bcd')
BOT_TOKEN = environ.get('BOT_TOKEN', '7598643423:AAEP6IeplxW-aE0jrW8xnaC59ug0kaPt4H8')
TERABOX_API = environ.get('TERABOX_API', 'https://zozo-api.onrender.com/download?url=')

# Create downloads directory
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Initialize Pyrogram client
bot = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize FastAPI
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Bot is running"}

@app.get("/ping")
async def ping():
    return {"status": "ok"}

# Helper function to convert bytes to human-readable format
def human_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

# Progress callback for uploads
async def progress_callback(current, total, message, status, filename):
    percent = current * 100 / total
    progress_bar = "▓" * int(percent // 10) + "░" * (10 - int(percent // 10))
    try:
        await status.edit(
            f"📤 Uploading: `{filename}`\n"
            f"{progress_bar} {percent:.1f}%\n"
            f"📦 Size: {human_readable_size(total)}"
        )
    except Exception as e:
        logger.error(f"Error updating progress: {e}")

# Download function using aria2c
async def aria2_download(url, filename, out_dir):
    filepath = os.path.join(out_dir, filename)
    
    # Remove existing file if any
    if os.path.exists(filepath):
        os.remove(filepath)
    
    # aria2c command
    cmd = [
        "aria2c",
        "--dir=" + out_dir,
        "--out=" + filename,
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--continue=true",
        "--allow-overwrite=true",
        url
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    await process.wait()
    
    if os.path.exists(filepath):
        return filepath
    return None

# Start command handler
@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    await message.reply_text(
        "👋 Hello! I'm your TeraBox Download Bot.\n\n"
        "📥 Just send me a TeraBox link and I'll download and upload it to you at high speed.\n\n"
        "🚀 Built for speed and reliability!"
    )

# Main download handler
@bot.on_message(filters.private & filters.text)
async def handle_terabox_link(client: Client, message: Message):
    url = message.text.strip()
    logger.info(f"Received URL: {url}")
    
    # Check if it's a TeraBox link
    if not ("terabox.com" in url or "1024terabox.com" in url):
        await message.reply("❌ Please send a valid TeraBox link.")
        return
    
    status = await message.reply("🔍 Processing your link...")
    
    try:
        # Step 1: Get direct download link from API
        await status.edit("🔗 Getting download information from API...")
        api_url = f"{TERABOX_API}{url}"
        logger.info(f"Calling API: {api_url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status != 200:
                    error_msg = f"API Error: Status {response.status}"
                    logger.error(error_msg)
                    await status.edit(f"❌ {error_msg}")
                    return
                
                data = await response.json()
                logger.info(f"API Response: {data}")
                
                if "download_link" not in data:
                    await status.edit("❌ No download link found in API response")
                    return
                
                download_url = data["download_link"]
                filename = data.get("name", "terabox_file.mkv")
                size = data.get("size", "Unknown")
                thumbnail = data.get("thumbnail", None)
        
        # Step 2: Download the file
        await status.edit(f"⏬ Downloading: `{filename}`\n📦 Size: {size}")
        filepath = await aria2_download(download_url, filename, DOWNLOAD_DIR)
        
        if not filepath or not os.path.exists(filepath):
            await status.edit("❌ Failed to download the file")
            return
        
        # Step 3: Upload the file to Telegram
        await status.edit(f"📤 Preparing to upload: `{filename}`")
        
        # Get actual file size
        actual_size = os.path.getsize(filepath)
        human_size = human_readable_size(actual_size)
        
        # Upload with progress
        await client.send_document(
            chat_id=message.chat.id,
            document=filepath,
            caption=f"✅ {filename}\n📦 Size: {human_size}",
            progress=lambda c, t: asyncio.create_task(
                progress_callback(c, t, message, status, filename)
            )
        )
        
        # Clean up
        await status.delete()
        os.remove(filepath)
        logger.info(f"Successfully sent file: {filename}")
        
    except aiohttp.ClientError as e:
        logger.error(f"Network error: {e}")
        await status.edit(f"❌ Network error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await status.edit(f"❌ An error occurred: {str(e)}")
    finally:
        # Ensure file is deleted even if error occurs
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)

# Run both FastAPI and Pyrogram
async def run_bot_and_server():
    await bot.start()
    logger.info("🤖 Telegram bot started!")
    
    config = uvicorn.Config(app, host="0.0.0.0", port=8080)
    server = uvicorn.Server(config)
    
    await server.serve()

if __name__ == "__main__":
    # Check if aria2c is installed
    try:
        subprocess.run(["aria2c", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("aria2c is not installed or not in PATH. Please install aria2 first.")
        exit(1)
    
    asyncio.run(run_bot_and_server())
