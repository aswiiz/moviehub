import asyncio
import os
from pyrogram import Client
from dotenv import load_dotenv

async def test():
    load_dotenv()
    session = os.getenv("TELEGRAM_STRING_SESSION")
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    
    print(f"Testing session starting with: {session[:10]}...")
    
    app = Client("test", session_string=session, api_id=int(api_id), api_hash=api_hash)
    try:
        async with app:
            me = await app.get_me()
            print(f"✅ Success! Session belongs to: {me.first_name} (@{me.username or 'No Username'})")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
