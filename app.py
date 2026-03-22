from flask import Flask, request, jsonify, Response, render_template
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from pyrogram import Client
import requests
import config
import re
import asyncio
import os
import indexer  # Import our indexing logic

app = Flask(__name__)
CORS(app)

# MongoDB Setup
try:
    client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client.get_database()
except Exception as e:
    print(f"MongoDB Configuration Error: {e}")
    client = MongoClient()
    db = client.moviehub
movies_collection = db.movies
settings_collection = db.settings
files_collection = db.files

# Pyrogram Client for Streaming & Indexing
is_vercel = os.getenv("VERCEL") == "1"
session_name = "/tmp/moviehub_bot" if is_vercel else "moviehub_bot"

# Support for Userbot (String Session) on Vercel
string_session = os.getenv("TELEGRAM_STRING_SESSION")

if string_session:
    print("Using TELEGRAM_STRING_SESSION for Userbot mode.")
    pyro_app = Client(
        "moviehub_userbot",
        session_string=string_session,
        api_id=config.TELEGRAM_API_ID,
        api_hash=config.TELEGRAM_API_HASH
    )
else:
    pyro_app = Client(
        session_name,
        api_id=config.TELEGRAM_API_ID,
        api_hash=config.TELEGRAM_API_HASH,
        bot_token=config.TELEGRAM_BOT_TOKEN
    )

def require_api_key(f):
    def decorated_function(*args, **kwargs):
        key = request.args.get('key')
        if not key or key != config.API_KEY:
            return jsonify({"error": "Unauthorized", "message": "Invalid API Key"}), 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['GET'])
@require_api_key
def search():
    # Handle movie search (existing)
    q = request.args.get('q', '')
    if q:
        regex = re.compile(f".*{re.escape(q)}.*", re.IGNORECASE)
        results = movies_collection.find({"title": regex})
        movies = []
        for movie in results:
            movie['_id'] = str(movie['_id'])
            movies.append(movie)
        return jsonify(movies)

    # Handle file search (new requirement)
    query = request.args.get('query', '')
    if query:
        regex = re.compile(f".*{re.escape(query)}.*", re.IGNORECASE)
        results = files_collection.find({
            "$or": [
                {"file_name": regex},
                {"caption": regex}
            ]
        })
        files = []
        for f in results:
            f['_id'] = str(f['_id'])
            if 'indexed_at' in f:
                f['indexed_at'] = f['indexed_at'].isoformat()
            files.append(f)
        return jsonify(files)

    return jsonify([])

    return jsonify(movies)

@app.route('/file/<file_id>', methods=['GET'])
@require_api_key
def get_file_details(file_id):
    try:
        # Try finding by MongoDB _id first
        try:
            f = files_collection.find_one({"_id": ObjectId(file_id)})
        except:
            f = None
            
        # If not found, try finding by file_id (Telegram's file_id)
        if not f:
            f = files_collection.find_one({"file_id": file_id})
            
        if not f:
            return jsonify({"error": "Not Found", "message": "File not found"}), 404

        f['_id'] = str(f['_id'])
        if 'indexed_at' in f:
            f['indexed_at'] = f['indexed_at'].isoformat()
            
        return jsonify(f)
    except Exception as e:
        return jsonify({"error": "Internal Error", "message": str(e)}), 500

@app.route('/download/<movie_id>/<quality>', methods=['GET'])
@require_api_key
def download(movie_id, quality):
    try:
        movie = movies_collection.find_one({"_id": ObjectId(movie_id)})
        if not movie:
            return jsonify({"error": "Not Found", "message": "Movie not found"}), 404

        # Find the specific file with matching quality
        file_info = next((f for f in movie.get('files', []) if f['quality'] == quality), None)
        if not file_info:
            return jsonify({"error": "Not Found", "message": "Quality not found"}), 404

        file_id = file_info['file_id']
        
        # Stream the file back using Pyrogram
        def generate():
            # Use a helper function to run async pyrogram code
            async def stream_file():
                if not pyro_app.is_connected:
                    await pyro_app.start()
                
                # Get message by exploring or using some mapping? 
                # Actually Pyrogram has direct download by file_id if we have the message or just path?
                # Best way: get the message first. But we don't store message_id/chat_id.
                # However, file_id is sufficient for download_media in newer Pyrogram.
                
                async for chunk in pyro_app.stream_media(file_id):
                    yield chunk

            # Bridge async generator to sync
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            gen = stream_file()
            while True:
                try:
                    chunk = loop.run_until_complete(anext(gen))
                    yield chunk
                except StopAsyncIteration:
                    break
                except Exception as e:
                    print(f"Streaming error: {e}")
                    break

        # Get the filename (clean version of movie title)
        filename = f"{movie['title']} ({quality}).mp4".replace(" ", "_")
        
        return Response(generate(), 
                        content_type='video/mp4',
                        headers={"Content-Disposition": f"attachment; filename={filename}"})

    except Exception as e:
        return jsonify({"error": "Internal Error", "message": str(e)}), 500

@app.route('/index', methods=['GET'])
@require_api_key
def trigger_index():
    chat_id = request.args.get('chat_id')
    limit = request.args.get('limit', type=int, default=100)
    
    if not chat_id:
        return jsonify({"error": "Bad Request", "message": "chat_id is required"}), 400

    try:
        # We need to use a separate pyro client for indexing to avoid conflict with streaming
        # but in serverless, we can just start/stop as needed.
        async def run_indexing():
            if not pyro_app.is_connected:
                await pyro_app.start()
            
            # Use the refined indexing function from indexer
            # We pass the shared movies_collection
            count = 0
            # Note: We use a smaller limit for Vercel to avoid timeouts
            safe_limit = min(limit, 200) 
            
            # Initialize indexer.app
            import indexer
            indexer.app = pyro_app
            
            # We slightly modify index_channel logic here to be more 'inline'
            # Or just call the function if it's compatible
            from indexer import iter_messages, process_message
            async for message in iter_messages(chat_id, limit=safe_limit):
                if message and not message.empty and message.document:
                     process_message(message)
                     count += 1
            return count

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        processed_count = loop.run_until_complete(run_indexing())
        
        return jsonify({
            "status": "success",
            "message": f"Indexed {processed_count} files from {chat_id}",
            "count": processed_count
        })

    except Exception as e:
        return jsonify({"error": "Indexing Failed", "message": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if data.get('username') == 'admin' and data.get('password') == 'admin123':
        # In a real app, use sessions or JWT. For now, simple success.
        return jsonify({"status": "success", "token": "admin_token_123"})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/highlights', methods=['GET'])
def get_highlights():
    settings = settings_collection.find_one({"type": "highlights"})
    if not settings or not settings.get('movies'):
        return jsonify([])
    
    h_data = settings['movies']
    highlights = []
    
    for item in h_data:
        mid_or_name = item['movie_id']
        custom_poster = item.get('custom_poster')
        
        movie = None
        # 1. Try by ID
        try:
            if len(mid_or_name) == 24: # Likely ObjectId
                movie = movies_collection.find_one({"_id": ObjectId(mid_or_name)})
        except:
            pass
            
        # 2. Try by Name if ID failed
        if not movie:
            movie = movies_collection.find_one({"title": {"$regex": f"^{re.escape(mid_or_name)}$", "$options": "i"}})
            
        if movie:
            movie['_id'] = str(movie['_id'])
            if custom_poster:
                movie['poster'] = custom_poster
            highlights.append(movie)
            
    return jsonify(highlights)

@app.route('/api/admin/highlights', methods=['POST'])
@require_api_key
def update_highlights():
    # Expects list of {"movie_id": "...", "custom_poster": "..."}
    h_data = request.json.get('movies', [])
    if len(h_data) > 3:
        return jsonify({"error": "Max 3 highlights allowed"}), 400
    
    settings_collection.update_one(
        {"type": "highlights"},
        {"$set": {"movies": h_data}},
        upsert=True
    )
    return jsonify({"status": "success"})

@app.route('/api/admin/stats', methods=['GET'])
@require_api_key
def get_stats():
    # 1. Total movies
    total_movies = movies_collection.count_documents({})
    
    # 2. Unique channels (approximated by file_id structure or just unique channels)
    # Since we don't store channel_id directly in the movie doc in a clean way,
    # let's assume 'connected channels' is just a count of unique first-message-forwards.
    # For now, we'll list the movie titles as a proxy or just hardcode/estimate.
    # Better: list unique qualities or something. 
    # Let's just return total movies and DB size for now.
    
    # 3. DB Size (estimated)
    stats = db.command("dbstats")
    db_size = f"{round(stats['dataSize'] / (1024 * 1024), 2)} MB"
    
    return jsonify({
        "total_movies": total_movies,
        "db_size": db_size,
        "channels": ["Main Index Channel"] # Placeholder
    })

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
