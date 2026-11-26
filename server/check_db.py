import sqlite3
from pathlib import Path

db = Path(__file__).parent / "caredesk.db"
print("DB path:", db, "| exists:", db.exists())

conn = sqlite3.connect(db)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])

for (name,) in tables:
    rows = conn.execute(f"SELECT * FROM {name}").fetchall()
    print(f"\n{name}: {len(rows)} rows")
    for row in rows:
        print("  ", row)

conn.close()