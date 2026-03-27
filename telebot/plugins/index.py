import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
try:
    from database.mongodb import db
    from config import Config
except ImportError:
    from ..database.mongodb import db
    from ..config import Config

# Filter to detect media messages
media_filter = filters.document | filters.video | filters.audio

@Client.on_message(filters.command("index") & filters.user(Config.ADMINS))
async def index_handler(bot: Client, message: Message):
    """Manually index a channel/group."""
    if len(message.command) < 2:
        await message.reply_text("Usage: `/index <channel_id>`")
        return

    chat_id = message.command[1]
    try:
        chat_id = int(chat_id)
    except:
        pass # Handle username if provided

    indexing_msg = await message.reply_text(f"Starting indexing for {chat_id}...")
    
    count = 0
    duplicates = 0
    total = 0

    try:
        async for msg in bot.get_chat_history(chat_id):
            total += 1
            if msg.media:
                media = getattr(msg, msg.media.value)
                if media:
                    success = await db.save_file(media, chat_id, msg.id)
                    if success:
                        count += 1
                    else:
                        duplicates += 1
            
            # Update progress every 100 messages
            if total % 100 == 0:
                await indexing_msg.edit_text(f"Indexing in progress...\nTotal: {total}\nIndexed: {count}\nDuplicates: {duplicates}")
                await asyncio.sleep(1)

    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        await message.reply_text(f"Error during indexing: {e}")
        return

    await indexing_msg.edit_text(f"Indexing Completed!\nTotal Analyzed: {total}\nNewly Indexed: {count}\nDuplicates Skipped: {duplicates}")

@Client.on_message(filters.chat(Config.CHANNELS) & media_filter)
async def auto_index_handler(bot: Client, message: Message):
    """Automatically index new media in specified channels."""
    media = getattr(message, message.media.value)
    if media:
        await db.save_file(media, message.chat.id, message.id)
        print(f"Auto-indexed: {media.file_name}")
