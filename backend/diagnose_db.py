"""
Check DB using psycopg2 (sync) - no event loop issues.
"""
import psycopg2

DB = "host=ep-cool-surf-alid3jw5.c-3.eu-central-1.aws.neon.tech dbname=neondb user=neondb_owner password=npg_o0ndwfG9bDNq sslmode=require"

conn = psycopg2.connect(DB)
cur = conn.cursor()

print("\n=== USERS ===")
cur.execute("SELECT id, username, email, role, full_name FROM users ORDER BY created_at")
for row in cur.fetchall():
    print(f"  id={row[0]}")
    print(f"    user={row[1]}, email={row[2]}, role={row[3]}, name={row[4]}")

print("\n=== PLATFORM_CONNECTIONS ===")
cur.execute("""
    SELECT pc.id, pc.user_id, pc.platform, pc.display_name, pc.connection_status,
           u.username, u.email, u.full_name
    FROM platform_connections pc
    LEFT JOIN users u ON pc.user_id = u.id
    ORDER BY pc.created_at
""")
rows = cur.fetchall()
if not rows:
    print("  (empty)")
for r in rows:
    print(f"  {r[2]} | {r[3]} | status={r[4]}")
    print(f"    -> user_id={r[1]} | {r[5]} ({r[6]}) name={r[7]}")

cur.close()
conn.close()
