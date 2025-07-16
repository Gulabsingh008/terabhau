import os
import asyncio
import threading
import logging
from pathlib import Path
from typing import Optional
from telegram import Message
from telegram.error import FloodWait, FilePartMissing

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FileDownloaderBot:
    MAX_SIZE = 2 * 1024**3  # 2GB
    
    def __init__(self, bot):
        self.bot = bot
        self.active_downloads = {}
        self.lock = threading.Lock()
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)

    async def handle_file_request(self, data: dict, msg: Message, message: Message) -> None:
        try:
            file_name = data['name']
            size_bytes = self.parse_size(data['size'])
            download_link = data['download_link']
            
            if size_bytes > self.MAX_SIZE:
                await self.edit_message(msg, f"❌ File too large ({data['size']}). Max supported size is 2GB.")
                return

            await self.edit_message(msg, f"📥 Downloading: {file_name}\n📦 Size: {data['size']}\n⏳ This may take a while...")

            await asyncio.to_thread(
                self.process_download,
                msg, message, download_link, file_name
            )

        except Exception as e:
            logger.error(f'Processing error: {str(e)}')
            await self.edit_message(msg, f"❌ Error: {str(e)}")

    def process_download(self, msg: Message, message: Message, download_link: str, file_name: str) -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            file_path, success = self.download_file(download_link, file_name)
            if not success:
                loop.run_until_complete(
                    self.edit_message(msg, f"❌ Download failed for {file_name}")
                )
                return

            loop.run_until_complete(
                self.send_video(message, file_path, file_name)
            )
            
        except Exception as e:
            logger.error(f'Download error: {str(e)}')
            loop.run_until_complete(
                self.edit_message(msg, f"❌ Download error: {str(e)}")
            )
        finally:
            loop.close()

    def download_file(self, url: str, file_name: str) -> tuple:
        try:
            from aria2p import API
            aria2 = API(port=6800)
            download = aria2.add(url, dir=str(self.download_dir))
            
            while not download.is_complete:
                if download.status == "error":
                    return None, False
                time.sleep(1)
            
            return str(self.download_dir / file_name), True
            
        except Exception as e:
            logger.error(f"Aria2p error: {str(e)}")
            return None, False

    async def send_video(self, message: Message, file_path: str, file_name: str) -> None:
        status_msg = await message.reply_text(
            f"📤 Uploading: {file_name}\n"
            "⏳ Please wait..."
        )

        try:
            path = Path(file_path)
            if not path.exists():
                await self.edit_message(status_msg, f"❌ Upload failed: File not found at path: {file_path}")
                return

            me = await self.bot.get_me()
            await message.reply_video(
                video=str(path),
                caption=f"✅ {file_name}\n\nPowered by @{me.username}",
                supports_streaming=True,
                progress=self.upload_progress,
                progress_args=(status_msg, file_name)
            )
            await status_msg.delete()

        except FilePartMissing as e:
            await self.edit_message(status_msg, f"❌ Upload failed: {str(e)}")
        except Exception as e:
            await self.edit_message(status_msg, f"❌ Upload error: {str(e)}")
        finally:
            try:
                path = Path(file_path)
                if path.exists():
                    path.unlink()
            except Exception as e:
                logger.error(f"File cleanup failed: {str(e)}")

    async def upload_progress(self, current: int, total: int, msg: Message, file_name: str) -> None:
        percent = current * 100 / total
        progress_bar = "⬢" * int(percent / 5) + "⬡" * (20 - int(percent / 5))
        status = (
            f"📤 Uploading: {file_name}\n"
            f"{progress_bar}\n"
            f"📊 {self.human_size(current)} / {self.human_size(total)}"
            f" ({percent:.1f}%)"
        )
        try:
            if msg.text != status:
                await msg.edit_text(status)
        except Exception:
            pass

    async def edit_message(self, msg: Message, text: str) -> None:
        try:
            if msg.text != text:
                await msg.edit_text(text)
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            await msg.edit_text(text)
        except Exception as e:
            if "MESSAGE_NOT_MODIFIED" not in str(e):
                logger.error(f"Message edit failed: {str(e)}")

    @staticmethod
    def human_size(size: int) -> str:
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        index = 0
        while size >= 1024 and index < len(units) - 1:
            size /= 1024
            index += 1
        return f"{size:.2f} {units[index]}"

    @staticmethod
    def parse_size(size_str: str) -> int:
        units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
        num = float(''.join(filter(str.isdigit, size_str)))
        unit = ''.join(filter(str.isalpha, size_str.upper())))
        return int(num * units.get(unit, 1))
