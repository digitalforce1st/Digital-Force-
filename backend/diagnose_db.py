"""
Direct NeonDB diagnostic — checks what's in platform_connections right now.
"""
import asyncio
import asyncpg

DB_URL = "postgresql://neondb_owner:npg_o0ndwfG9bDNq@ep-cool-surf-alid3jw5.c-3.eu-central-1.aws.neon.tech/neondb"

async def main():
    conn = await asyncpg.connect(DB_URL, ssl="require")
    
    print("\n=== USERS ===")
    users = await conn.fetch("SELECT id, username, email FROM users")
    for u in users:
        print(f"  {u['id']} | {u['username']} | {u['email']}")

    print("\n=== PLATFORM_CONNECTIONS ===")
    rows = await conn.fetch("SELECT id, user_id, platform, display_name, connection_status, is_enabled FROM platform_connections")
    if not rows:
        print("  (empty — no accounts in DB)")
    for r in rows:
        print(f"  id={r['id'][:8]}... | user_id={str(r['user_id'])[:8] if r['user_id'] else 'NULL'} | {r['platform']} | {r['display_name']} | status={r['connection_status']} | enabled={r['is_enabled']}")

    await conn.close()

asyncio.run(main())
