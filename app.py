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

# Ensure an event loop exists for sync environments (like Gunicorn)
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import indexer  # Import our indexing logic

# Lazy initialization for Pyrogram Client
_pyro_app = None

app = Flask(__name__)
CORS(app)

# MongoDB Setup
try:
    mongo_uri = config.MONGO_URI
    if not mongo_uri or mongo_uri == "CHANGEME":
         print("WARNING: No valid MONGO_URI found. Falling back to local/default.")
         mongo_uri = "mongodb://localhost:27017/moviehub"
         
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    # Don't ping on import to avoid blocking gunicorn workers
    # client.admin.command('ping') 
    db = client.get_database()
except Exception as e:
    print(f"MongoDB Configuration Error: {e}")
    client = MongoClient()
    db = client.moviehub

movies_collection = db.movies
settings_collection = db.settings
files_collection = db.files

def get_pyro_app():
    global _pyro_app
    if _pyro_app:
        return _pyro_app
        
    session_name = "moviehub_bot"
    string_session = os.getenv("TELEGRAM_STRING_SESSION")
    
    try:
        if string_session:
            print("Using TELEGRAM_STRING_SESSION for Userbot mode.")
            _pyro_app = Client(
                "moviehub_userbot",
                session_string=string_session,
                api_id=config.TELEGRAM_API_ID,
                api_hash=config.TELEGRAM_API_HASH
            )
        else:
            if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "CHANGEME":
                print("WARNING: No TELEGRAM_BOT_TOKEN found. Pyrogram might fail.")
                
            _pyro_app = Client(
                session_name,
                api_id=config.TELEGRAM_API_ID,
                api_hash=config.TELEGRAM_API_HASH,
                bot_token=config.TELEGRAM_BOT_TOKEN
            )
    except Exception as e:
        print(f"Pyrogram Initialization Error: {e}")
        return None
        
    return _pyro_app

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
    import threading
    import tempfile
    import os as _os

    try:
        movie = movies_collection.find_one({"_id": ObjectId(movie_id)})
        if not movie:
            return jsonify({"error": "Not Found", "message": "Movie not found"}), 404

        # Find the specific file with matching quality
        file_info = next((f for f in movie.get('files', []) if f['quality'] == quality), None)
        if not file_info:
            # Fall back to default file if exact quality not found
            file_info = next((f for f in movie.get('files', []) if f.get('default')), None)
        if not file_info:
            return jsonify({"error": "Not Found", "message": "Quality not found"}), 404

        file_id = file_info['file_id']
        channel_id = file_info.get('channel_id')
        message_id = file_info.get('message_id')

        # --- Strategy 1: Use Pyrogram to download and serve the file ---
        result = {}
        error_holder = {}

        def run_download():
            async def _download():
                try:
                    client = indexer.get_client()
                    async with client:
                        if channel_id and message_id:
                            # Best path: get original message and download from it
                            msg = await client.get_messages(int(channel_id), int(message_id))
                            path = await client.download_media(msg, file_name=f"/tmp/{file_id[:20]}")
                        else:
                            # Fallback: download directly by file_id
                            path = await client.download_media(file_id, file_name=f"/tmp/{file_id[:20]}")
                        result['path'] = path
                except Exception as e:
                    error_holder['error'] = str(e)
            asyncio.run(_download())

        t = threading.Thread(target=run_download)
        t.start()
        t.join(timeout=300)  # 5 min timeout for large files

        if 'error' in error_holder:
            return jsonify({"error": "Download Failed", "message": error_holder['error']}), 500

        tmp_path = result.get('path')
        if not tmp_path or not _os.path.exists(tmp_path):
            return jsonify({"error": "Download Failed", "message": "File could not be retrieved from Telegram"}), 500

        # Serve the file
        file_size = _os.path.getsize(tmp_path)
        # Determine MIME type from extension
        ext = _os.path.splitext(tmp_path)[1].lower()
        mime_map = {'.mkv': 'video/x-matroska', '.mp4': 'video/mp4', '.avi': 'video/x-msvideo', '.mov': 'video/quicktime'}
        content_type = mime_map.get(ext, 'application/octet-stream')

        # Build a clean filename
        raw_name = f"{movie.get('title', 'movie')} ({quality}){ext}".replace(" ", "_").replace("/","_")

        def generate_file():
            try:
                with open(tmp_path, 'rb') as f:
                    while True:
                        chunk = f.read(1024 * 256)  # 256KB chunks
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    _os.remove(tmp_path)
                except Exception:
                    pass

        headers = {
            "Content-Disposition": f"attachment; filename=\"{raw_name}\"",
            "Content-Length": str(file_size),
        }
        return Response(generate_file(), content_type=content_type, headers=headers, direct_passthrough=True)

    except Exception as e:
        print(f"Download error: {e}")
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
            pyro_app = get_pyro_app()
            if not pyro_app:
                 raise Exception("Could not initialize Pyrogram app.")
                 
            if not pyro_app.is_connected:
                await pyro_app.start()
            
            # Use the refined indexing function from indexer
            # We pass the shared movies_collection
            count = 0
            # Note: We use a limit to avoid long-running requests on some platforms
            safe_limit = min(limit, 500) 
            
            # Initialize indexer.app
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

@app.route('/api/admin/movies', methods=['GET'])
@require_api_key
def get_admin_movies():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    skip = (page - 1) * limit

    results = movies_collection.find().sort("title", 1).skip(skip).limit(limit)
    
    movies = []
    for m in results:
        m['_id'] = str(m['_id'])
        movies.append(m)
        
    return jsonify(movies)

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
