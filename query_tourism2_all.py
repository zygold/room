import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT s.name, c.name as class_name, sc.chinese_score, sc.math_score, sc.english_score,
           sc.professional_score, sc.total_score
    FROM scores sc
    JOIN students s ON sc.student_id = s.id
    JOIN classes c ON s.class_id = c.id
    WHERE sc.exam_id = 13 AND c.name LIKE '%旅游2%'
    ORDER BY s.name
""").fetchall()

for r in rows:
    print(dict(r))

conn.close()
