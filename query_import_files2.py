import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print('=== import_files schema ===')
rows = conn.execute("PRAGMA table_info(import_files)").fetchall()
for r in rows:
    print(dict(r))

print('\n=== All import files ===')
rows = conn.execute("SELECT * FROM import_files ORDER BY id DESC LIMIT 20").fetchall()
for r in rows:
    print(dict(r))

conn.close()
