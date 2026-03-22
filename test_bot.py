import asyncio
import config
from pyrogram import Client

async def test():
    print("Testing bot connectivity...")
    string_session = getattr(config, "TELEGRAM_STRING_SESSION", None)
    
    if string_session:
        print("Using TELEGRAM_STRING_SESSION for test...")
        app = Client(
            "test_userbot",
            session_string=string_session,
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH,
            in_memory=True
        )
    else:
        app = Client(
            "test_session",
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH,
            bot_token=config.TELEGRAM_BOT_TOKEN,
            in_memory=True
        )
    try:
        await app.start()
        me = await app.get_me()
        print(f"Successfully connected as: {me.first_name} (@{me.username})")
        await app.stop()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
