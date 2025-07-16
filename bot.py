import os
import aiohttp
import asyncio
import shutil
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from math import ceil

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TERABOX_API = os.getenv("TERABOX_API")  # Your API endpoint

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def aria2_download(url, out_dir):
    file_name = ""
    cmd = [
        "aria2c", "--dir=" + out_dir,
        "--max-connection-per-server=16",
        "--split=16", "--min-split-size=1M",
        "--continue", url
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = await process.communicate()

    for line in stdout.decode().split("\n"):
        if "[#DL" in line and "Download complete" in line:
            for word in line.split():
                if word.endswith(".mp4") or word.endswith(".mkv"):
                    file_name = word
    return os.path.join(out_dir, file_name) if file_name else None

def progress_bar(progress, total):
    percent = progress * 100 / total
    bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
    return f"[{bar}] {percent:.1f}%"

app = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.private & filters.text)
async def handle(client: Client, message: Message):
    link = message.text.strip()
    if "terabox" not in link:
        return await message.reply("❌ Invalid TeraBox link.")

    status = await message.reply("🔍 Getting Download Link...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TERABOX_API + link) as resp:
                data = await resp.json()
                dlink = data["download_link"]
                name = data.get("name", "file.mkv")
                fsize = data.get("size", "Unknown")
        
        await status.edit(f"⏬ **Downloading:** `{name}`\n📦 Size: `{fsize}`")

        filepath = await aria2_download(dlink, DOWNLOAD_DIR)

        if not filepath or not os.path.exists(filepath):
            return await status.edit("❌ Failed to download file.")

        async def upload_progress(current, total):
            bar = progress_bar(current, total)
            await status.edit(f"⏫ **Uploading:** `{name}`\n{bar}")

        await client.send_document(
            chat_id=message.chat.id,
            document=filepath,
            caption=f"✅ Done: `{name}`\n📦 Size: `{fsize}`",
            progress=upload_progress
        )

        await status.delete()
        os.remove(filepath)

    except Exception as e:
        await status.edit(f"❌ Error: {e}")

app.run()
