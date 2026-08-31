import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print('=== subject_standards ===')
rows = conn.execute("SELECT * FROM subject_standards").fetchall()
for r in rows:
    print(dict(r))

print('\n=== majors ===')
rows = conn.execute("SELECT id, name FROM majors").fetchall()
for r in rows:
    print(dict(r))

conn.close()
