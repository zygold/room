import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT id, name FROM classes WHERE name LIKE '%旅游2%'").fetchall()
for r in rows:
    print(dict(r))

conn.close()
