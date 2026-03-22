from pymongo import MongoClient
import config
from bson.objectid import ObjectId

def seed():
    try:
        client = MongoClient(config.MONGO_URI)
        db = client.get_database()
        
        movies_collection = db.movies
        settings_collection = db.settings
        
        # 1. Create Sample Movies
        sample_movies = [
            {
                "title": "Inception",
                "year": 2010,
                "poster": "https://m.media-amazon.com/images/M/MV5BMjAxMzY3NjcxNF5BMl5BanBnXkFtZTcwNTI5OTM0Mw@@._V1_SX300.jpg",
                "files": [
                    {"quality": "1080p", "file_id": "file_id_inception_1080", "size": "2.4 GB", "default": True},
                    {"quality": "720p", "file_id": "file_id_inception_720", "size": "1.2 GB", "default": False}
                ]
            },
            {
                "title": "Interstellar",
                "year": 2014,
                "poster": "https://m.media-amazon.com/images/M/MV5BZjdkOTU3MDktN2IxOS00OGEyLWFmMjktY2FiMmZkNWIyODZiXkEyXkFqcGdeQXVyMTMxODk2OTU@._V1_SX300.jpg",
                "files": [
                    {"quality": "1080p", "file_id": "file_id_interstellar_1080", "size": "3.1 GB", "default": True}
                ]
            },
            {
                "title": "The Dark Knight",
                "year": 2008,
                "poster": "https://m.media-amazon.com/images/M/MV5BMTMxNTMwODM0NF5BMl5BanBnXkFtZTcwODAyMTk2Mw@@._V1_SX300.jpg",
                "files": [
                    {"quality": "1080p", "file_id": "file_id_tdk_1080", "size": "2.8 GB", "default": True}
                ]
            }
        ]
        
        # Insert movies if they don't exist
        movie_ids = []
        for m in sample_movies:
            existing = movies_collection.find_one({"title": m["title"]})
            if not existing:
                res = movies_collection.insert_one(m)
                movie_ids.append(str(res.inserted_id))
                print(f"Inserted movie: {m['title']}")
            else:
                movie_ids.append(str(existing["_id"]))
                print(f"Movie already exists: {m['title']}")
        
        # 2. Update Highlights
        highlights_data = []
        for mid in movie_ids:
            highlights_data.append({"movie_id": mid})
            
        settings_collection.update_one(
            {"type": "highlights"},
            {"$set": {"movies": highlights_data}},
            upsert=True
        )
        print("Updated highlights with seeded movies.")
        
    except Exception as e:
        print(f"Error seeding database: {e}")

if __name__ == "__main__":
    seed()
