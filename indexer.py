import re
import requests
from pyrogram import Client
from pymongo import MongoClient
import config
import time
import os
import asyncio

from datetime import datetime, timezone

# MongoDB Setup
try:
    client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    # Ping to check if host is valid
    client.admin.command('ping')
    db = client.get_database()
except Exception as e:
    print(f"MongoDB Configuration Error: {e}")
    # Fallback/Dummy for initialization
    client = MongoClient() 
    db = client.moviehub
movies_collection = db.movies
files_collection = db.files

# In-memory storage for last forwarded chat per user
last_forwarded_chat = {}

def get_client():
    is_vercel = os.getenv("VERCEL") == "1"
    session_name = "/tmp/moviehub_bot" if is_vercel else "moviehub_bot"
    
    # 1. Prioritize String Session (Userbot)
    string_session = getattr(config, 'TELEGRAM_STRING_SESSION', None)
    if string_session:
        print("Using TELEGRAM_STRING_SESSION for indexing client.")
        return Client(
            "moviehub_userbot",
            session_string=string_session,
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH
        )
        
    # 2. Check for bot token
    bot_token = config.TELEGRAM_BOT_TOKEN
    if not bot_token or bot_token == "CHANGEME":
        print("NOTE: No Bot Token found. Switching to USERBOT mode (interactive login).")
        return Client(
            session_name,
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH
        )
    
    return Client(
        session_name,
        api_id=config.TELEGRAM_API_ID,
        api_hash=config.TELEGRAM_API_HASH,
        bot_token=bot_token
    )

# Global client (will be initialized in main)
app = None

def clean_title(filename):
    """
    Cleans filename: replaces dots/underscores with spaces,
    removes unwanted tags and extracts year.
    """
    # Replace dots/underscores with spaces
    title = filename.replace(".", " ").replace("_", " ")
    
    # Extract year (1900-2099)
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
    year = int(year_match.group(1)) if year_match else None
    
    # Remove year from title
    if year_match:
        title = title.replace(year_match.group(1), "")
    
    # Remove unwanted tags
    tags = [
        "480p", "720p", "1080p", "2160p", "HDRip", "BluRay", 
        "x264", "x265", "WEB-DL", "WEBRip", "Dual", "Audio", 
        "HINDI", "ENGLISH", "ESub", "HEVC", "EXTENDED", "BDRip"
    ]
    for tag in tags:
        title = re.sub(rf'\b{tag}\b', '', title, flags=re.IGNORECASE)
    
    # Final cleanup: remove extra spaces
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title, year

def detect_quality(filename):
    """Detects quality from filename."""
    if "2160" in filename: return "2160p"
    if "1080" in filename: return "1080p"
    if "720" in filename: return "720p"
    if "480" in filename: return "480p"
    return "Unknown"

def format_size(size_bytes):
    """Converts bytes to human readable format."""
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def fetch_imdb_data(title):
    """Fetches movie data from IMDb API."""
    try:
        url = f"{config.IMDB_API_URL}{title}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                # Return the first match
                match = data[0]
                return {
                    "title": match.get("title"),
                    "year": int(match.get("year")) if match.get("year") else None,
                    "poster": match.get("poster")
                }
    except Exception as e:
        print(f"IMDb API Error for {title}: {e}")
    return None

def process_message(message):
    """Processes a single Telegram message containing a document."""
    if not message.document:
        return

    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size

    # Check for duplicate file_id
    if movies_collection.find_one({"files.file_id": file_id}):
        print(f"Skipping duplicate file: {file_name}")
        return

    # 1. Clean filename
    cleaned_title, extracted_year = clean_title(file_name)
    
    # 2. Detect quality
    quality = detect_quality(file_name)
    
    # 3. Format size
    readable_size = format_size(file_size)

    # 4. IMDb Auto Match or Fallback
    # Check if movie already exists in DB to reuse poster/IMDb data
    existing_movie = movies_collection.find_one({"title": {"$regex": f"^{re.escape(cleaned_title)}$", "$options": "i"}})
    
    if existing_movie and existing_movie.get("poster"):
        poster = existing_movie.get("poster")
        final_title = existing_movie.get("title")
        final_year = existing_movie.get("year")
    else:
        # Fetch from IMDb API
        imdb_data = fetch_imdb_data(cleaned_title)
        if imdb_data:
            final_title = imdb_data["title"]
            final_year = imdb_data["year"] or extracted_year
            poster = imdb_data["poster"]
        else:
            final_title = cleaned_title
            final_year = extracted_year
            poster = None

    # 5. Prepare file entry
    file_entry = {
        "quality": quality,
        "file_id": file_id,
        "size": readable_size,
        "default": False # Will set default logic later
    }

    # 6. Insert or Update MongoDB
    if existing_movie:
        # Update existing movie: avoid duplicate quality
        if not any(f['quality'] == quality for f in existing_movie.get('files', [])):
            movies_collection.update_one(
                {"_id": existing_movie["_id"]},
                {"$push": {"files": file_entry}}
            )
            # Update default quality logic
            update_default_quality(existing_movie["_id"])
            print(f"Indexed: {final_title} ({quality}) - Added to existing")
        else:
            print(f"Skipping: {final_title} ({quality}) - Quality already exists")
    else:
        # Create new movie entry
        movie_data = {
            "title": final_title,
            "year": final_year,
            "poster": poster,
            "files": [file_entry]
        }
        result = movies_collection.insert_one(movie_data)
        update_default_quality(result.inserted_id)
        print(f"Indexed: {final_title} ({quality}) - New entry")

def process_file_message(message):
    """Processes a single Telegram message for generic file indexing."""
    if not message.document and not message.video and not message.audio:
        return

    file = message.document or message.video or message.audio
    file_id = file.file_id
    file_name = getattr(file, 'file_name', 'Untitled')
    file_size = format_size(file.file_size)
    file_type = file.mime_type or "unknown"
    caption = message.caption or ""
    channel_id = str(message.chat.id)
    message_id = message.id
    date = message.date

    # Prepare file record
    file_record = {
        "file_id": file_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "file_name": file_name,
        "caption": caption,
        "file_type": file_type,
        "size": file_size,
        "indexed_at": datetime.now(timezone.utc)
    }

    # Upsert record (using file_id as unique key)
    files_collection.update_one(
        {"file_id": file_id},
        {"$set": file_record},
        upsert=True
    )
    print(f"File Indexed/Updated: {file_name}")

def update_default_quality(movie_id):
    """Sets 720p as default if available, otherwise first file."""
    movie = movies_collection.find_one({"_id": movie_id})
    if not movie or not movie.get("files"):
        return

    files = movie["files"]
    
    # Reset all defaults
    for f in files: f["default"] = False
    
    # Find 720p
    idx_720 = next((i for i, f in enumerate(files) if f["quality"] == "720p"), None)
    
    if idx_720 is not None:
        files[idx_720]["default"] = True
    else:
        files[0]["default"] = True
        
    movies_collection.update_one(
        {"_id": movie_id},
        {"$set": {"files": files}}
    )

async def iter_messages(chat_id, limit, offset=0):
    """
    Yields messages from a chat by fetching them in batches.
    Works backwards from the latest message if offset is 0.
    """
    try:
        if app is None:
            raise Exception("Indexer client 'app' is not initialized. Please set indexer.app before calling.")
        
        # Get the latest message ID first
        chat = await app.get_chat(chat_id)
        last_id = chat.last_message_id
        print(f"DEBUG: Last Message ID in {chat_id} is {last_id}")
    except Exception as e:
        print(f"Error getting chat info for {chat_id}: {e}")
        return

    current = last_id if offset == 0 else offset
    total_fetched = 0

    while total_fetched < limit and current > 0:
        batch_size = min(200, limit - total_fetched)
        start_id = max(1, current - batch_size + 1)
        ids = list(range(start_id, current + 1))
        
        try:
            messages = await app.get_messages(chat_id, ids)
            # Reverse batch to go backwards
            for message in reversed(messages):
                yield message
                total_fetched += 1
                if total_fetched >= limit:
                    break
            
            current = start_id - 1
        except Exception as e:
            print(f"Error fetching batch near {current}: {e}")
            break

# Remove the decorator, we will use add_handler instead
async def handle_message(client, message):
    """Handles search queries or forwarded messages for indexing with robust error catching."""
    try:
        # Logging basics
        user_id = message.from_user.id if message.from_user else 'Unknown'
        text = message.text or ""
        print(f"DEBUG: Processing message from {user_id}: {text[:50]}")
        
        # Admin check for all sensitive operations
        is_admin = (config.ADMIN_ID and user_id == config.ADMIN_ID)
        
        # 1. Detection of File/Channel for Indexing
        # Triggered when admin forwards a message from a channel OR sends a file directly (if not private chat)
        source_chat_id = None
        source_name = None

        if message.forward_from_chat:
            source_chat_id = message.forward_from_chat.id
            source_name = getattr(message.forward_from_chat, 'title', getattr(message.forward_from_chat, 'username', 'Private Chat'))
        elif (message.document or message.video or message.audio) and message.chat.type != "private":
            # If a file is sent in a group/channel where bot is present
            source_chat_id = message.chat.id
            source_name = getattr(message.chat, 'title', 'This Group')

        if source_chat_id and is_admin:
            print(f"DEBUG: Setting target channel for admin {user_id} to {source_chat_id}")
            last_forwarded_chat[user_id] = source_chat_id
            await message.reply_text(f"📥 **Channel Detected**\nSource: `{source_name or source_chat_id}`\nID: `{source_chat_id}`\n\nSend `/index` to start indexing this channel.")
            return

        # 2. Command Handling
        if text.startswith('/'):
            if text == "/start":
                await message.reply_text("Welcome to MOVIE HUB! \n\n1. Search for a file/movie.\n2. **Forward/Send** a file from a channel to detect it, then send `/index`!")
                return
            
            elif text.startswith('/index'):
                if not is_admin:
                    return await message.reply_text("❌ Unauthorized. Admin only.")

                parts = text.split()
                target_chat = None
                target_limit = None

                if len(parts) > 1:
                    target_chat = parts[1]
                    if len(parts) > 2:
                        target_limit = int(parts[2])
                else:
                    target_chat = last_forwarded_chat.get(user_id)
                
                if not target_chat:
                    return await message.reply_text("❌ No channel detected. Forward a message/file from a channel first, or use `/index <chat_id>`.")

                await message.reply_text(f"🚀 **Indexing Started**\nTarget: `{target_chat}`\n\nThis may take a moment...")
                asyncio.create_task(index_channel(target_chat, limit=target_limit))
                return

        # 3. Search handling
        if message.text:
            query = message.text
            results = list(movies_collection.find({
                "title": {"$regex": f".*{re.escape(query)}.*", "$options": "i"}
            }).limit(10))

            if not results:
                await message.reply_text("No movies found for your search.")
            else:
                response_text = f"🔍 Search results for: **{query}**\n\n"
                for movie in results:
                    response_text += f"🎬 **{movie['title']}** ({movie.get('year', 'N/A')})\n"
                    for f in movie.get('files', []):
                         response_text += f"  └ {f['quality']} - {f['size']}\n"
                    response_text += "\n"
                await message.reply_text(response_text)

    except Exception as e:
        print(f"CRITICAL ERROR in handle_message: {e}")
        try:
            # Tell the user/admin about the error if possible
            await message.reply_text(f"❌ **Handler Error**: {e}")
        except:
            pass

async def index_channel(chat_id, limit=None, offset_id=0):
    """Indexes full channel history or range using batch retrieval."""
    count = 0
    print(f"DEBUG: Starting index_channel for {chat_id} (Limit: {limit})")
    try:
        if config.ADMIN_ID:
            await app.send_message(config.ADMIN_ID, f"🚀 **Indexing Started**\nTarget: `{chat_id}`\nMethod: Batch Retrieval")

        # 2. Check if client is bot vs user
        me = await app.get_me()
        is_bot = me.is_bot if me else True
        
        if is_bot:
            print(f"INFO: Running as BOT (@{getattr(me, 'username', 'Unknown')}). Using batch retrieval.")
            async for message in iter_messages(chat_id, limit=limit, offset=offset_id):
                if message and not message.empty:
                    if message.document or message.video or message.audio:
                        process_file_message(message)
                        count += 1
                        if count % 20 == 0:
                            print(f"Progress: Indexed {count} files...")
        else:
            print(f"INFO: Running as USER ({me.first_name}). Using standard history crawl.")
            async for message in app.get_chat_history(chat_id, limit=limit, offset_id=offset_id):
                if message and not message.empty:
                    if message.document or message.video or message.audio:
                        process_file_message(message)
                        count += 1
                        if count % 20 == 0:
                            print(f"Progress: Indexed {count} files...")
        
        print(f"Indexing complete. Processed {count} files.")
        
        # Notify admin if possible
        if config.ADMIN_ID:
            try:
                await app.send_message(config.ADMIN_ID, f"✅ Indexing complete for ID: `{chat_id}`\nProcessed: **{count}** files.")
            except Exception as e:
                print(f"Failed to notify admin: {e}")
    except Exception as e:
        print(f"Error during indexing {chat_id}: {e}")
        if config.ADMIN_ID:
            await app.send_message(config.ADMIN_ID, f"❌ Error during indexing: {e}")

async def main():
    import sys
    global app
    
    # 1. Validate configuration
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "MONGO_URI"]
    missing = [var for var in required if not getattr(config, var, None)]
    
    if missing:
        print(f"CRITICAL ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    # 2. Initialize app inside the loop
    app = get_client()
    
    # 3. Register handlers
    from pyrogram.handlers import MessageHandler
    app.add_handler(MessageHandler(handle_message))

    # 4. Handle command line arguments
    if len(sys.argv) > 1:
        # Example: python3 indexer.py -100123456789 1000
        chat = sys.argv[1]
        try:
            # Try to convert to int if it looks like an ID
            if chat.startswith("-100") or chat.isdigit():
                chat = int(chat)
        except:
            pass
            
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
        off = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        
        async with app:
            print(f"Starting DIRECT indexing for {chat}...")
            await index_channel(chat, lim, off)
    else:
        print("Bot started. Listening for messages...")
        await app.start()
        from pyrogram import idle
        await idle()
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal Error: {e}")
