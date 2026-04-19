import asyncio
import httpx

async def check():
    print("Testing Uvicorn...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/health", timeout=3.0)
            print("Status:", resp.status_code)
            print("Body:", resp.text)
    except Exception as e:
        print("Error:", e)

asyncio.run(check())
