import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    db_url = "postgresql+asyncpg://neondb_owner:npg_o0ndwfG9bDNq@ep-cool-surf-alid3jw5.c-3.eu-central-1.aws.neon.tech/neondb?ssl=require"
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT user_id, autonomous_mode FROM agency_settings"))
        print("agency_settings:", res.fetchall())
        
        res = await conn.execute(text("SELECT id, username FROM users"))
        print("users:", res.fetchall())

if __name__ == "__main__":
    asyncio.run(main())
