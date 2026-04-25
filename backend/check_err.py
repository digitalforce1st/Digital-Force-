import asyncio
from database import async_session, KnowledgeItem
from sqlalchemy import select

async def run():
    async with async_session() as db:
        res = await db.execute(select(KnowledgeItem))
        items = res.scalars().all()
        for i in items:
            print(f"ID: {i.id} | Status: {i.processing_status} | Error: {i.error_message}")

if __name__ == "__main__":
    asyncio.run(run())
