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

# Pyrogram Client for Streaming
# Vercel needs sessions in /tmp as the filesystem is read-only
is_vercel = os.getenv("VERCEL") == "1"
session_name = "/tmp/moviehub_bot" if is_vercel else "moviehub_bot"

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
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    # Case-insensitive regex search
    regex = re.compile(f".*{re.escape(query)}.*", re.IGNORECASE)
    results = movies_collection.find({"title": regex})

    movies = []
    for movie in results:
        movie['_id'] = str(movie['_id'])
        movies.append(movie)
    
    return jsonify(movies)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
