import asyncio
import os
from pyrogram import Client
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    
    if not api_id or not api_hash:
        print("❌ Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in your .env file.")
        print("Please visit https://my.telegram.org and create an app to get them.")
        return

    print("--- Movie Hub String Session Generator ---")
    print(f"Using API ID: {api_id}")
    print(f"Using API Hash: {api_hash}")
    print("\nFollow the instructions to log in to your personal Telegram account.")
    print("This session will be used for indexing channel history.")
    
    async with Client(":memory:", api_id=int(api_id), api_hash=api_hash) as app:
        session_string = await app.export_session_string()
        print("\n" + "="*50)
        print("✅ SUCCESS! Your STRING_SESSION is below:")
        print("="*50 + "\n")
        print(session_string)
        print("\n" + "="*50)
        print("👉 Copy the string above and add it to your .env file as:")
        print('TELEGRAM_STRING_SESSION="your_session_string_here"')
        print("="*50)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Error: {e}")
