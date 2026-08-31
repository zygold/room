import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

print('DB_PATH:', DB_PATH)
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Find student 杨卿
student_rows = conn.execute("SELECT s.id, s.name, c.name as class_name FROM students s JOIN classes c ON s.class_id = c.id WHERE s.name LIKE '%杨卿%'").fetchall()
print('Students named 杨卿:', [dict(r) for r in student_rows])

for stu in student_rows:
    sid = stu['id']
    print(f'\n=== Scores for student {sid} ===')
    score_rows = conn.execute("""
        SELECT sc.*, e.name as exam_name, e.exam_date
        FROM scores sc
        JOIN exams e ON sc.exam_id = e.id
        WHERE sc.student_id = ?
    """, (sid,)).fetchall()
    for r in score_rows:
        print(dict(r))

# Also search scores by name if any
print('\n=== All scores where professional looks like 学号 ===')
rows = conn.execute("""
    SELECT sc.id, s.name, sc.professional, c.name as class_name, e.name as exam_name
    FROM scores sc
    JOIN students s ON sc.student_id = s.id
    JOIN classes c ON s.class_id = c.id
    JOIN exams e ON sc.exam_id = e.id
    WHERE sc.professional > 1000000
""").fetchall()
print('Abnormally large professional scores:', [dict(r) for r in rows])

conn.close()
