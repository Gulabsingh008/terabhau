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

API_ID = int(environ.get('API_ID', '26494161'))
API_HASH = environ.get('API_HASH', '55da841f877d16a3a806169f3c5153d3')
BOT_TOKEN = environ.get('BOT_TOKEN', '8191032269:AAEM4nJdIpPCPx3LODpb9wo9RK2MD5VCicY')
TERABOX_API = environ.get('TERABOX_API', 'https://zozo-api.onrender.com/download?url=')

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ✅ /start command handler
@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    await message.reply_text(
        "👋 Hello! I'm your TeraBox Download Bot.\n\n"
        "📥 Just send me a TeraBox link and I'll download and upload it to you at high speed.\n\n"
        "🚀 Built for speed and style!"
    )

# ✅ TeraBox download handler
@bot.on_message(filters.private & filters.text)
async def handle(client: Client, message: Message):
    print("📩 Received:", message.text)

    url = message.text.strip()
    if "terabox" not in url:
        return await message.reply("❌ Invalid TeraBox link.")

    status = await message.reply("🔍 Getting Direct Download Link...")

    try:
        print("🔗 Calling API:", TERABOX_API + url)
        async with aiohttp.ClientSession() as session:
            async with session.get(TERABOX_API + url) as resp:
                data = await resp.json()
                print("✅ API response:", data)
                dlink = data["download_link"]
                name = data.get("name", "file.mkv")
                fsize = data.get("size", "Unknown")

        await status.edit(f"⏬ **Downloading:** `{name}`\n📦 Size: `{fsize}`")

        filepath = await aria2_download(dlink, DOWNLOAD_DIR)
        if not filepath or not os.path.exists(filepath):
            return await status.edit("❌ Failed to download the file.")

        # Progress bar generator
        def progress_bar(current, total):
            percent = current * 100 / total if total else 0
            filled = int(percent // 10)
            return f"[{'█' * filled}{'░' * (10 - filled)}] {percent:.1f}%"

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
        print("✅ File sent and cleaned:", filepath)

    except Exception as e:
        print("❌ Error:", e)
        await status.edit(f"❌ Error: {e}")

# ✅ Aria2 download function
async def aria2_download(url, out_dir):
    cmd = [
        "aria2c", "--dir=" + out_dir,
        "--max-connection-per-server=16",
        "--split=16", "--min-split-size=1M",
        "--continue", "--allow-overwrite=true",
        url
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = await process.communicate()

    for line in stdout.decode().split("\n"):
        if "Download complete" in line:
            for word in line.split():
                if word.endswith((".mkv", ".mp4", ".zip", ".rar", ".mp3")):
                    return os.path.join(out_dir, word)
    return None

# ✅ FastAPI server
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Bot is running"}

@app.get("/ping")
def ping():
    return {"status": "ok"}

# ✅ Run bot in thread-safe way
def run_bot():
    asyncio.run(start_bot())

async def start_bot():
    await bot.start()
    print("🤖 Telegram bot started!")
    await bot.send_message("me", "✅ Bot is live and running!")
    await bot.idle()

def run_web():
    uvicorn.run(app, host="0.0.0.0", port=8080)

# ✅ Start both
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    run_web()
