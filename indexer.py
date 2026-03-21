import re
import requests
from pyrogram import Client
from pymongo import MongoClient
import config
import time

# MongoDB Setup
client = MongoClient(config.MONGO_URI)
try:
    # Try to get database from URI
    db = client.get_default_database()
except Exception:
    # Fallback to 'moviehub' if not specified in URI
    db = client.moviehub
movies_collection = db.movies

# Pyrogram Client Setup
import os
is_vercel = os.getenv("VERCEL") == "1"
session_name = "/tmp/moviehub_bot" if is_vercel else "moviehub_bot"

app = Client(
    session_name,
    api_id=config.TELEGRAM_API_ID,
    api_hash=config.TELEGRAM_API_HASH,
    bot_token=config.TELEGRAM_BOT_TOKEN
)

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

@app.on_message()
async def handle_message(client, message):
    """Handles search queries from users."""
    if not message.text or message.text.startswith('/'):
        if message.text == "/start":
            await message.reply_text("Welcome to MOVIE HUB! Send me a movie name to search.")
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
            # Since bot can't send direct links to file_ids for download easily via HTTP 
            # without a bot browser or a specialized bot flow, we just list them.
            response_text += f"  └ {f['quality']} - {f['size']}\n"
        response_text += "\n"
    
    await message.reply_text(response_text)

async def index_channel(chat_id, limit=None, offset_id=0):
    """Indexes full channel history or range."""
    count = 0
    async with app:
        async for message in app.get_chat_history(chat_id, limit=limit, offset_id=offset_id):
            if message.document and any(message.document.mime_type.startswith(x) for x in ["video/", "application/"]):
                process_message(message)
                count += 1
    print(f"Indexing complete. Processed {count} messages.")

if __name__ == "__main__":
    import asyncio
    # For manual testing/command line usage
    # usage: python indexer.py <chat_id> [limit] [offset_id]
    import sys
    if len(sys.argv) > 1:
        chat = sys.argv[1]
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
        off = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        asyncio.run(index_channel(chat, lim, off))
    else:
        print("Bot started. Listening for messages...")
        app.run()
