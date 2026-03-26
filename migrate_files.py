import indexer
from pymongo import MongoClient
import config
import time

def migrate():
    print("Starting migration from 'files' collection to 'movies' collection...")
    
    # Setup MongoDB
    try:
        client = MongoClient(config.MONGO_URI)
        db = client.get_database()
        files_collection = db.files
        movies_collection = db.movies
    except Exception as e:
        print(f"MongoDB Error: {e}")
        return

    # Count files to migrate
    total_files = files_collection.count_documents({})
    print(f"Total files found in 'files' collection: {total_files}")
    
    if total_files == 0:
        print("No files to migrate.")
        return

    count = 0
    skipped = 0
    errors = 0

    # Iterate over all files
    for file_doc in files_collection.find():
        file_id = file_doc.get('file_id')
        file_name = file_doc.get('file_name', 'Untitled')
        file_size = file_doc.get('size') # This is already formatted string
        
        if not file_id:
            print(f"Skipping file without file_id: {file_name}")
            skipped += 1
            continue
            
        try:
            # Call the refactored process_file_info from indexer
            # We use is_formatted=True because 'size' in 'files' coll is already a string like "1.2 GB"
            indexer.process_file_info(file_id, file_name, file_size, is_formatted=True)
            count += 1
            if count % 50 == 0:
                print(f"Progress: Migrated {count}/{total_files} files...")
                # Small sleep to avoid hitting IMDb API too hard if many new movies
                time.sleep(1) 
        except Exception as e:
            print(f"Error migrating {file_name}: {e}")
            errors += 1

    print("\nMigration Complete!")
    print(f"Successfully processed: {count}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")
    
    # Final check
    new_movie_count = movies_collection.count_documents({})
    print(f"New total movies in 'movies' collection: {new_movie_count}")

if __name__ == "__main__":
    migrate()
