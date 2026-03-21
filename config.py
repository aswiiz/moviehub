import os
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

# Configuration for Movie Hub

# MongoDB Connection String
MONGO_URI = os.getenv("MONGO_URI", "")

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Telegram API ID and Hash for Userbot (Pyrogram)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
if TELEGRAM_API_ID:
    TELEGRAM_API_ID = int(TELEGRAM_API_ID)

TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# IMDb API URL
IMDB_API_URL = "https://api.imdbapi.dev/search?query="

# Simple API Key Protection
API_KEY = os.getenv("MOVIEHUB_API_KEY", "CHANGEME")
