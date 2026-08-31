import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Find the exam for 2025-2026 second semester midterm
print('=== Exams containing 期中/半期/第二学期 ===')
exams = conn.execute("SELECT * FROM exams WHERE name LIKE '%第二学期%' AND (name LIKE '%期中%' OR name LIKE '%半期%')").fetchall()
for e in exams:
    print(dict(e))

if exams:
    exam_id = exams[0]['id']
    print(f'\n=== exam_subject_configs for exam_id={exam_id} ===')
    configs = conn.execute("SELECT * FROM exam_subject_configs WHERE exam_id=?", (exam_id,)).fetchall()
    for c in configs:
        print(dict(c))

    print(f'\n=== Sample scores for 旅游2班 in exam_id={exam_id} ===')
    rows = conn.execute("""
        SELECT s.name, c.name as class_name, sc.chinese_score, sc.math_score, sc.english_score,
               sc.professional_score, sc.professional_max_score, sc.professional_converted,
               sc.total_score, sc.is_converted
        FROM scores sc
        JOIN students s ON sc.student_id = s.id
        JOIN classes c ON s.class_id = c.id
        WHERE sc.exam_id = ? AND c.name LIKE '%旅游2%'
        ORDER BY s.name
        LIMIT 10
    """, (exam_id,)).fetchall()
    for r in rows:
        print(dict(r))

conn.close()
