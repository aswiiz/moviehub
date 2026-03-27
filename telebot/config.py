import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.environ.get("API_ID", 37562086))
    API_HASH = os.environ.get("API_HASH", "09bc4b5e0cbf9a17ef99248ee60f05cb")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "5559626039:AAEkYvWGRJcT7oPe9fIAX0tnj88Vn_-Nn00")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Vercel-Admin-healthcare-hub:terminator@healthcare-hub.oa7qjqu.mongodb.net/moviehub?appName=healthcare-hub")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "moviehub")
    COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "files")
    
    # List of channel IDs to auto-index (optional)
    CHANNELS = [int(ch) for ch in os.environ.get("CHANNELS", "").split()] if os.environ.get("CHANNELS") else []
    
    # Admin IDs
    ADMINS = [int(admin) for admin in os.environ.get("ADMINS", "7759011110").split()] if os.environ.get("ADMINS") else []
