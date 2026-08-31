import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print('=== All scores with professional_score between 15 and 25 in exam 13 ===')
rows = conn.execute("""
    SELECT s.name, c.name as class_name, sc.professional_score, sc.professional_max_score, sc.total_score
    FROM scores sc
    JOIN students s ON sc.student_id = s.id
    JOIN classes c ON s.class_id = c.id
    WHERE sc.exam_id = 13 AND sc.professional_score BETWEEN 15 AND 25
    ORDER BY c.name, s.name
    LIMIT 30
""").fetchall()
for r in rows:
    print(dict(r))

conn.close()
