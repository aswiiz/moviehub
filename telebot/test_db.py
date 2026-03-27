import asyncio
from database.mongodb import db
from config import Config

async def test():
    print(f"Connecting to MongoDB at {Config.MONGO_URI}...")
    try:
        # Check connection
        await db.client.admin.command('ping')
        print("MongoDB connection successful!")
        
        # Test collection
        count = await db.col.count_documents({})
        print(f"Current document count in {Config.COLLECTION_NAME}: {count}")
        
    except Exception as e:
        print(f"MongoDB connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
