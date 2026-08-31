import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print('=== Classes containing 计算机/电/数 ===')
rows = conn.execute("""
    SELECT id, name, grade_id, major_id, class_type_id
    FROM classes
    WHERE name LIKE '%计算机%' OR name LIKE '%电%' OR name LIKE '%数%'
    ORDER BY name
""").fetchall()
for r in rows:
    print(dict(r))

print('\n=== Class count by major ===')
rows = conn.execute("""
    SELECT m.name as major_name, COUNT(c.id) as cnt
    FROM classes c
    JOIN majors m ON c.major_id = m.id
    GROUP BY c.major_id
    ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(dict(r))

conn.close()
