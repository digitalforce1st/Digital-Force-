import asyncio
from database import async_session, KnowledgeItem
from sqlalchemy import select

async def run():
    async with async_session() as db:
        res = await db.execute(select(KnowledgeItem).where(KnowledgeItem.processing_status == "processing"))
        items = res.scalars().all()
        for i in items:
            i.processing_status = "failed"
            i.error_message = "Upload was interrupted when the backend restarted. Please delete and upload again."
        await db.commit()
        print(f"Reset {len(items)} stuck items to failed.")

if __name__ == "__main__":
    asyncio.run(run())
