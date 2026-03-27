import re
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
try:
    from config import Config
except ImportError:
    from ..config import Config

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(Config.MONGO_URI)
        self.db = self.client[Config.DATABASE_NAME]
        self.col = self.db[Config.COLLECTION_NAME]

    async def save_file(self, media, chat_id, message_id):
        """Save file metadata to MongoDB."""
        file_id = media.file_id
        file_name = media.file_name or "Unknown"
        file_size = media.file_size
        caption = media.caption if hasattr(media, 'caption') else ""

        # Clean filename for better search results
        clean_name = self.clean_file_name(file_name)

        file_data = {
            "file_id": file_id,
            "file_name": file_name,
            "clean_name": clean_name,
            "file_size": file_size,
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
            "indexed_at": datetime.now()
        }

        try:
            # Use file_id as a unique identifier if possible, or just insert
            # To avoid duplicates, we can check if it exists first
            if not await self.col.find_one({"file_id": file_id}):
                await self.col.insert_one(file_data)
                return True
        except Exception as e:
            print(f"Error saving file: {e}")
        return False

    def clean_file_name(self, name):
        """Standardize filename for searching."""
        name = re.sub(r'(_|\-|\.|\+)', ' ', name)
        return name.lower().strip()

    async def search_files(self, query, offset=0, limit=10):
        """Search files using regex on clean_name."""
        clean_query = self.clean_file_name(query)
        # Create a regex that matches the query parts
        regex_query = ".*".join(clean_query.split())
        
        cursor = self.col.find({"clean_name": {"$regex": regex_query, "$options": "i"}})
        cursor.skip(offset).limit(limit)
        
        results = await cursor.to_list(length=limit)
        total = await self.col.count_documents({"clean_name": {"$regex": regex_query, "$options": "i"}})
        
        return results, total

db = Database()
