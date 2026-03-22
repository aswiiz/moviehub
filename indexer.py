import re
import requests
from pyrogram import Client
from pymongo import MongoClient
import config
import time
import os

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

def get_client():
    is_vercel = os.getenv("VERCEL") == "1"
    session_name = "/tmp/moviehub_bot" if is_vercel else "moviehub_bot"
    return Client(
        session_name,
        api_id=config.TELEGRAM_API_ID,
        api_hash=config.TELEGRAM_API_HASH,
        bot_token=config.TELEGRAM_BOT_TOKEN
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
    Useful for bots that cannot use get_chat_history.
    """
    current = offset
    while True:
        # Fetch in batches of 200 (Telegram limit for get_messages)
        new_diff = min(200, limit - current)
        if new_diff <= 0:
            return
            
        # Create a list of message IDs to fetch
        ids = list(range(current + 1, current + new_diff + 1))
        try:
            messages = await app.get_messages(chat_id, ids)
            for message in messages:
                yield message
                current += 1
        except Exception as e:
            print(f"Error fetching batch {current}-{current+new_diff}: {e}")
            return # Stop on fatal error

# Remove the decorator, we will use add_handler instead
async def handle_message(client, message):
    """Handles search queries or forwarded messages for indexing."""
    print(f"DEBUG: Received message from {message.from_user.id if message.from_user else 'Unknown'}: {message.text or '[No Text]'}")
    if message.forward_from_chat:
        print(f"DEBUG: Message is FORWARDED from {message.forward_from_chat.id} ({message.forward_from_chat.title})")
    
    # 1. Check for forwarded messages (to start indexing)
    if message.forward_from_chat:
        chat = message.forward_from_chat
        last_msg_id = message.forward_from_message_id
        await message.reply_text(f"Detected forward from: **{chat.title}** (ID: `{chat.id}`)\nLast Message ID: `{last_msg_id}`\nAttempting to index history...")
        
        asyncio.create_task(index_channel(chat.id, limit=last_msg_id))
        return

    # 2. Handle commands
    if message.text and message.text.startswith('/'):
        if message.text == "/start":
            await message.reply_text("Welcome to MOVIE HUB! \n\n1. Send me a movie name to search.\n2. **Forward a message from a channel** to start indexing its files!\n3. Use `/index <chat_id> <last_id>` for manual indexing.")
        
        elif message.text.startswith('/index'):
            parts = message.text.split()
            if len(parts) < 3:
                return await message.reply_text("Usage: `/index <chat_id> <last_msg_id>`")
            
            try:
                target_chat = parts[1]
                target_last_id = int(parts[2])
                await message.reply_text(f"Starting manual indexing for `{target_chat}` up to ID `{target_last_id}`...")
                asyncio.create_task(index_channel(target_chat, limit=target_last_id))
            except ValueError:
                await message.reply_text("Last message ID must be a number.")
        return

    query = message.text
    results = list(movies_collection.find({
        "title": {"$regex": f".*{re.escape(query)}.*", "$options": "i"}
    }).limit(10))

    if not results:
        await message.reply_text("No movies found for your search.")
        return

    response_text = f"🔍 Search results for: **{query}**\n\n"
    for movie in results:
        response_text += f"🎬 **{movie['title']}** ({movie.get('year', 'N/A')})\n"
        for f in movie.get('files', []):
            response_text += f"  └ {f['quality']} - {f['size']}\n"
        response_text += "\n"
    
    await message.reply_text(response_text)

async def index_channel(chat_id, limit=None, offset_id=0):
    """Indexes full channel history or range using batch retrieval."""
    count = 0
    print(f"DEBUG: Starting index_channel for {chat_id} (Limit: {limit})")
    try:
        if config.ADMIN_ID:
            await app.send_message(config.ADMIN_ID, f"🚀 **Indexing Started**\nTarget: `{chat_id}`\nMethod: Batch Retrieval")

        # Use our new batch iterator
        async for message in iter_messages(chat_id, limit=limit, offset=offset_id):
            if message and not message.empty and message.document and any(message.document.mime_type.startswith(x) for x in ["video/", "application/"]):
                process_message(message)
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
        chat = sys.argv[1]
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
        off = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        
        async with app:
            print(f"Starting indexing for {chat}...")
            await index_channel(chat, lim, off)
    else:
        print("Bot started. Listening for messages...")
        await app.start()
        from pyrogram import idle
        await idle()
        await app.stop()

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal Error: {e}")
