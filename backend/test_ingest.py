import asyncio
from rag.pipeline import ingest
import logging
logging.basicConfig(level=logging.DEBUG)

async def test():
    print("STARTING")
    result = await ingest("text", "Hello this is a test document", "12345")
    print("DONE", result)

if __name__ == "__main__":
    asyncio.run(test())
