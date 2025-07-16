import os
import aiohttp
import asyncio
import subprocess
from os import environ
from pyrogram import Client, filters
from pyrogram.types import Message
from fastapi import FastAPI
import uvicorn
import threading

# ✅ ENV or fallback values
API_ID = int(environ.get('API_ID', '24519654'))
API_HASH = environ.get('API_HASH', '1ccea9c29a420df6a6622383fbd83bcd')
BOT_TOKEN = environ.get('BOT_TOKEN', '7598643423:AAEP6IeplxW-aE0jrW8xnaC59ug0kaPt4H8')
TERABOX_API = environ.get('TERABOX_API', 'https://zozo-api.onrender.com/download?url=')

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ✅ Aria2 Downloader
async def aria2_download(url, out_dir):
    cmd = [
        "aria2c", "--dir=" + out_dir,
        "--max-connection-per-server=16",
        "--split=16", "--min-split-size=1M",
        "--continue",
        "--allow-overwrite=true",
        url
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = await process.communicate()
    
    for line in stdout.decode().split("\n"):
        if "Download complete" in line:
            for word in line.split():
                if word.endswith((".mkv", ".mp4", ".zip", ".rar")):
                    return os.path.join(out_dir, word)
    return None

# ✅ Progress bar
def progress_bar(progress, total):
    percent = progress * 100 / total
    bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
    return f"[{bar}] {percent:.1f}%"

# ✅ Start Telegram Bot
bot = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.private & filters.text)
async def handle(client: Client, message: Message):
    url = message.text.strip()
    if "terabox" not in url:
        return await message.reply("❌ Invalid TeraBox link.")

    status = await message.reply("🔍 Getting Download Link...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TERABOX_API + url) as resp:
                data = await resp.json()
                dlink = data["download_link"]
                name = data.get("name", "file.mkv")
                fsize = data.get("size", "Unknown")

        await status.edit(f"⏬ **Downloading:** `{name}`\n📦 Size: `{fsize}`")

        filepath = await aria2_download(dlink, DOWNLOAD_DIR)
        if not filepath or not os.path.exists(filepath):
            return await status.edit("❌ Failed to download file.")

        async def progress(current, total):
            bar = progress_bar(current, total)
            await status.edit(f"⏫ **Uploading:** `{name}`\n{bar}")

        await client.send_document(
            chat_id=message.chat.id,
            document=filepath,
            caption=f"✅ Done: `{name}`\n📦 Size: `{fsize}`",
            progress=progress
        )

        await status.delete()
        os.remove(filepath)

    except Exception as e:
        await status.edit(f"❌ Error: {e}")

# ✅ Dummy Web Server for Render Port Bind
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Bot is running"}

@app.get("/ping")
def ping():
    return {"status": "ok"}

# ✅ Run Bot + FastAPI together
def run_bot():
    bot.run()

def run_web():
    uvicorn.run(app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    run_web()
