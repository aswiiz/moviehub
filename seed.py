from pymongo import MongoClient
import config

# Sample data to seed MongoDB for testing
sample_movies = [
    {
        "title": "Avatar: The Way of Water",
        "year": 2022,
        "imdb_id": "tt1630029",
        "files": [
            {"quality": "480p", "file_id": "BQACAgUAAxkBAAIB...", "size": "500MB", "default": False},
            {"quality": "720p", "file_id": "BQACAgUAAxkBAAIB...", "size": "1.2GB", "default": True},
            {"quality": "1080p", "file_id": "BQACAgUAAxkBAAIB...", "size": "2.5GB", "default": False}
        ]
    },
    {
        "title": "Interstellar",
        "year": 2014,
        "imdb_id": "tt0816692",
        "files": [
            {"quality": "720p", "file_id": "BQACAgUAAxkBAAIB...", "size": "1.5GB", "default": True},
            {"quality": "1080p", "file_id": "BQACAgUAAxkBAAIB...", "size": "3.0GB", "default": False}
        ]
    },
    {
        "title": "Inception",
        "year": 2010,
        "imdb_id": "tt1375666",
        "files": [
            {"quality": "480p", "file_id": "BQACAgUAAxkBAAIB...", "size": "450MB", "default": False},
            {"quality": "1080p", "file_id": "BQACAgUAAxkBAAIB...", "size": "2.1GB", "default": True}
        ]
    }
]

def seed_db():
    client = MongoClient(config.MONGO_URI)
    db = client.get_database()
    collection = db.movies
    
    # Clear existing data (optional, but good for testing)
    collection.delete_many({})
    
    # Insert sample data
    result = collection.insert_many(sample_movies)
    print(f"Successfully seeded {len(result.inserted_ids)} movies.")

if __name__ == "__main__":
    seed_db()
