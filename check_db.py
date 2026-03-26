from pymongo import MongoClient
import config
import os

try:
    client = MongoClient(config.MONGO_URI)
    db = client.get_database()
    settings = db.settings.find_one({"type": "highlights"})
    print(f"Highlights in DB: {settings}")
    
    movies_count = db.movies.count_documents({})
    print(f"Total movies in DB (movies collection): {movies_count}")
    
    files_count = db.files.count_documents({})
    print(f"Total files in DB (files collection): {files_count}")
    
    if movies_count > 0:
        sample_movie = db.movies.find_one()
        print(f"Sample movie: {sample_movie.get('title')} (_id: {sample_movie.get('_id')})")

    if files_count > 0:
        sample_file = db.files.find_one()
        print(f"Sample file: {sample_file.get('file_name')} (file_id: {sample_file.get('file_id')})")
except Exception as e:
    print(f"Error: {e}")
