import asyncio
from database import engine, async_session, PlatformConnection
from sqlalchemy import select

async def check():
    async with async_session() as session:
        stmt = select(PlatformConnection)
        result = await session.execute(stmt)
        accounts = result.scalars().all()
        print(f"Total Accounts: {len(accounts)}")
        for a in accounts:
             print(f"- {a.id} | {a.display_name} | {a.platform} | {a.connection_status}")

if __name__ == "__main__":
    asyncio.run(check())
