import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT s.id, s.name, c.name as class_name, e.name as exam_name, e.school_year, e.semester, e.exam_type, e.exam_date,
           sc.chinese_score, sc.math_score, sc.english_score, sc.professional_score, sc.total_score
    FROM scores sc
    JOIN students s ON sc.student_id = s.id
    JOIN classes c ON s.class_id = c.id
    JOIN exams e ON sc.exam_id = e.id
    WHERE s.name LIKE '%杨卿%'
    ORDER BY e.exam_date, e.id
""").fetchall()

print('All 杨卿 scores in database:')
for r in rows:
    print(dict(r))

conn.close()
