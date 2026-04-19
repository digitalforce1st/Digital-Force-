import sqlite3
import sys

def run():
    try:
        conn = sqlite3.connect("digitalforce.db")
        conn.execute("ALTER TABLE published_posts ADD COLUMN connection_id VARCHAR")
        conn.commit()
        conn.close()
        print("Successfully added connection_id to SQLite DB!")
    except Exception as e:
        if "duplicate column name" in str(e):
            print("Column exists!")
        else:
            print("Error:", e)

if __name__ == "__main__":
    run()
