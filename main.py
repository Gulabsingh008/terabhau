import os
import aiohttp
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = int(os.getenv('API_ID', '24519654'))
API_HASH = os.getenv('API_HASH', '1ccea9c29a420df6a6622383fbd83bcd')
BOT_TOKEN = os.getenv('BOT_TOKEN', '7598643423:AAEP6IeplxW-aE0jrW8xnaC59ug0kaPt4H8')
TERABOX_API = os.getenv('TERABOX_API', 'https://zozo-api.onrender.com/download?url=')
DOWNLOAD_DIR = "downloads"

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Initialize bot
bot = Client(
    "terabox_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=2
)

@bot.on_message(filters.command("start") & filters.private)
async def start(client: Client, message: Message):
    try:
        await message.reply("🚀 TeraBox Download Bot is running!")
        logger.info(f"Responded to start command from {message.from_user.id}")
    except Exception as e:
        logger.error(f"Start command error: {e}")

@bot.on_message(filters.text & filters.private)
async def handle_message(client: Client, message: Message):
    try:
        logger.info(f"Received message: {message.text}")
        
        if "terabox" not in message.text.lower():
            await message.reply("Please send a TeraBox link")
            return
            
        await message.reply("🔍 Processing your TeraBox link...")
        
        # Test API call
        async with aiohttp.ClientSession() as session:
            test_url = f"{TERABOX_API}https://example.terabox.com"
            async with session.get(test_url) as resp:
                logger.info(f"API test status: {resp.status}")
                await message.reply(f"API test response: {resp.status}")
                
    except Exception as e:
        logger.error(f"Message handling error: {e}")
        await message.reply(f"Error: {str(e)}")

async def main():
    await bot.start()
    logger.info("Bot started successfully")
    await bot.send_message("me", "🤖 Bot is now online!")
    await bot.idle()

if __name__ == "__main__":
    # Verify essential requirements
    try:
        import pyrogram
        import aiohttp
        logger.info("All imports working")
    except ImportError as e:
        logger.error(f"Import error: {e}")
        exit(1)

    asyncio.run(main())
