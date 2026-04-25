import asyncio
from database import async_session, KnowledgeItem
from sqlalchemy import select

async def run():
    item_id = "b2ea4405-2fa9-4eb1-9283-ece85de06e17"
    async with async_session() as db:
        item = await db.get(KnowledgeItem, item_id)
        print("Before update:", item.processing_status)
        item.processing_status = "indexed"
        await db.commit()
        print("Commit finished.")
    
    # Re-read
    async with async_session() as db2:
        item2 = await db2.get(KnowledgeItem, item_id)
        print("After reread:", item2.processing_status)

if __name__ == "__main__":
    asyncio.run(run())
