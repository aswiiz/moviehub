import sys
import os
from pyrogram import Client

# Add the current directory to sys.path to handle imports when run from root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Change CWD to the directory of main.py to handle relative paths correctly
os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    from config import Config
except ImportError:
    from .config import Config

import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Bot(Client):
    def __init__(self):
        session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexing_bot")
        super().__init__(
            session_path,
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins={"root": "plugins"}
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        logger.info(f"Bot started as @{me.username}")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    bot = Bot()
    bot.run()
