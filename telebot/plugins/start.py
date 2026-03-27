from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(bot: Client, message: Message):
    await message.reply_text(
        f"Hello {message.from_user.mention}!\n\n"
        "I am a File Indexing Bot. I can scan channels and index files into a database for searching.\n\n"
        "Commands:\n"
        "/index - Start indexing a channel (Admin only)\n"
        "/search <query> - Search for files\n"
        "/help - Get help"
    )

@Client.on_message(filters.command("help"))
async def help_handler(bot: Client, message: Message):
    await message.reply_text(
        "**How to use:**\n"
        "1. Add me to your channel as an admin.\n"
        "2. Use `/index` in the channel to index all existing files.\n"
        "3. New files sent after indexing will be auto-indexed.\n"
        "4. Use `/search <filename>` to find files."
    )
