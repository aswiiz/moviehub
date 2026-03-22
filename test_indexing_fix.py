import asyncio
import app
from indexer import iter_messages
import config

async def test_indexing():
    print("Testing indexing connection...")
    chat_id = "aswiiz_bot_logs" # Example channel or a known ID from .env
    # Usually you'd use a real ID here.
    
    # Check if pyro_app can connect
    try:
        import indexer
        indexer.app = app.pyro_app
        print(f"indexer.app set to: {indexer.app}")
        
        if indexer.app is None:
            print("FAILED: indexer.app is still None")
        else:
            print("SUCCESS: indexer.app is initialized")
        
    except Exception as e:
        print(f"Indexing test failed: {e}")

    finally:
        if app.pyro_app.is_connected:
            await app.pyro_app.stop()

if __name__ == "__main__":
    asyncio.run(test_indexing())
