import os
import aiohttp
import asyncio
import shutil
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from os import environ

API_ID = int(environ.get('API_ID', '24519654'))  # default fallback
API_HASH = environ.get('API_HASH', '1ccea9c29a420df6a6622383fbd83bcd')
BOT_TOKEN = environ.get('BOT_TOKEN', '7598643423:AAEP6IeplxW-aE0jrW8xnaC59ug0kaPt4H8')
TERABOX_API = environ.get('TERABOX_API', 'https://zozo-api.onrender.com/download?url=')


# ✅ Temp folder
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 🔁 Aria2 Download
async def aria2_download(url, out_dir):
    cmd = [
        "aria2c", "--dir=" + out_dir,
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--continue",
        "--allow-overwrite=true",
        url
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = await process.communicate()
    
    # Find downloaded filename
    for line in stdout.decode().split("\n"):
        if "Download complete" in line:
            parts = line.strip().split()
            for part in parts:
                if part.endswith(".mkv") or part.endswith(".mp4"):
                    return os.path.join(out_dir, part)
    return None

# 🔁 Progress bar
def progress_bar(progress, total):
    percent = progress * 100 / total
    bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
    return f"[{bar}] {percent:.1f}%"

# ✅ Start Bot
app = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.private & filters.text)
async def downloader(client: Client, message: Message):
    url = message.text.strip()
    if "terabox.com" not in url:
        return await message.reply("❌ Please send a valid TeraBox link.")

    status = await message.reply("🔍 Fetching download link...")

    try:
        # 1. Call your API
        async with aiohttp.ClientSession() as session:
            async with session.get(TERABOX_API + url) as resp:
                data = await resp.json()
                direct_link = data["download_link"]
                file_name = data.get("name", "file.mkv")
                file_size = data.get("size", "Unknown")

        await status.edit(f"⏬ **Downloading:** `{file_name}`\n📦 Size: `{file_size}`")

        # 2. Download with aria2
        downloaded_file = await aria2_download(direct_link, DOWNLOAD_DIR)
        if not downloaded_file or not os.path.exists(downloaded_file):
            return await status.edit("❌ Download failed.")

        # 3. Upload with progress
        async def progress(current, total):
            bar = progress_bar(current, total)
            await status.edit(f"⏫ **Uploading:** `{file_name}`\n{bar}")

        await client.send_document(
            chat_id=message.chat.id,
            document=downloaded_file,
            caption=f"✅ Done: `{file_name}`\n📦 Size: `{file_size}`",
            progress=progress
        )

        await status.delete()
        os.remove(downloaded_file)

    except Exception as e:
        await status.edit(f"❌ Error: {e}")

app.run()
