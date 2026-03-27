from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
try:
    from database.mongodb import db
except ImportError:
    from ..database.mongodb import db

@Client.on_message(filters.command("search") | filters.text & filters.private)
async def search_handler(bot: Client, message: Message):
    """Search for files in the database."""
    query = message.text
    if message.command:
        if len(message.command) < 2:
            await message.reply_text("Usage: `/search <filename>`")
            return
        query = " ".join(message.command[1:])
    
    if query.startswith("/"):
        return # Ignore other commands

    results, total = await db.search_files(query)
    
    if not results:
        await message.reply_text(f"No files found for '{query}'")
        return

    response = f"**Found {total} results for '{query}':**\n\n"
    for i, file in enumerate(results):
        size_mb = round(file['file_size'] / (1024 * 1024), 2)
        # We can create a link to the message if we have the chat username or link
        # For now, just display name and size.
        response += f"{i+1}. `{file['file_name']}` ({size_mb} MB)\n"
    
    await message.reply_text(response)

@Client.on_inline_query()
async def inline_search(bot: Client, query):
    if not query.query:
        return
    
    results, total = await db.search_files(query.query)
    
    inline_results = []
    for file in results:
        inline_results.append(
            InlineQueryResultArticle(
                title=file['file_name'],
                description=f"Size: {round(file['file_size']/(1024*1024), 2)} MB",
                input_message_content=InputTextMessageContent(
                    f"**File:** `{file['file_name']}`\n"
                    f"**Size:** {round(file['file_size']/(1024*1024), 2)} MB\n"
                    f"**Chat ID:** `{file['chat_id']}`\n"
                    f"**Message ID:** `{file['message_id']}`"
                )
            )
        )
    
    await query.answer(results=inline_results, cache_time=1)
