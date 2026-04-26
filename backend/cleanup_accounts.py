"""
Clean up duplicate platform connections in NeonDB.
Keep the most recent 'connected' record, remove older duplicates.
"""
import psycopg2

DB = "host=ep-cool-surf-alid3jw5.c-3.eu-central-1.aws.neon.tech dbname=neondb user=neondb_owner password=npg_o0ndwfG9bDNq sslmode=require"

conn = psycopg2.connect(DB)
cur = conn.cursor()

print("=== BEFORE CLEANUP ===")
cur.execute("SELECT id, display_name, connection_status, created_at FROM platform_connections ORDER BY created_at")
for r in cur.fetchall():
    print(f"  {r[0][:8]}... | {r[1]} | {r[2]} | {r[3]}")

# Find and delete duplicates - keep the best status one per (display_name, platform)
# Strategy: for each group of (user_id, platform, display_name), keep the most recent one
# that has 'connected' status, delete the rest

cur.execute("""
    DELETE FROM platform_connections
    WHERE id IN (
        SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id, display_name, platform
                       ORDER BY
                           CASE connection_status WHEN 'connected' THEN 0 ELSE 1 END,
                           created_at DESC
                   ) AS rn
            FROM platform_connections
        ) ranked
        WHERE rn > 1
    )
""")
deleted = cur.rowcount
conn.commit()
print(f"\n=== Deleted {deleted} duplicate rows ===")

print("\n=== AFTER CLEANUP ===")
cur.execute("SELECT id, display_name, connection_status, created_at FROM platform_connections ORDER BY created_at")
for r in cur.fetchall():
    print(f"  {r[0][:8]}... | {r[1]} | {r[2]} | {r[3]}")

cur.close()
conn.close()
