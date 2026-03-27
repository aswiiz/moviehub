# Telegram File Indexing Bot

A Telegram bot to index files from channels into MongoDB for easy searching.

## Setup

1. Clone or copy the files to your server.
2. `pip install -r requirements.txt`
3. Create a `.env` file based on `.env.example`.
4. Run `python3 main.py`.

## Commands

- `/start` - Start the bot.
- `/index <id>` - Index a channel (Admins only).
- `/search <query>` - Search for files.
- `/help` - Usage instructions.

## Tech Stack
- Python 3.8+
- Pyrogram (Telegram MTProto UI)
- Motor (Asynchronous MongoDB Driver)
- MongoDB
