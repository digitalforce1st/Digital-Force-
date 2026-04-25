import asyncio
from database import async_session, KnowledgeItem
from sqlalchemy import select

async def run():
    async with async_session() as db:
        res = await db.execute(select(KnowledgeItem))
        items = res.scalars().all()
        for i in items:
            if str(i.id) == '5638b4cc-6c8e-465f-afb9-24f90493aee2':
                print(f"ID: {i.id} | Status: {i.processing_status} | Title: {i.title} | Chunks: {i.chunk_count}")

if __name__ == "__main__":
    asyncio.run(run())
