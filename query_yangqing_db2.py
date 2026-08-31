import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

print('DB_PATH:', DB_PATH)
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# List all exams
print('\n=== All exams ===')
exams = conn.execute("SELECT * FROM exams ORDER BY id").fetchall()
for e in exams:
    print(dict(e))

# Find all 杨卿 in all students
print('\n=== All students named 杨卿 ===')
rows = conn.execute("""
    SELECT s.id, s.name, c.name as class_name, g.name as grade_name, m.name as major_name
    FROM students s
    JOIN classes c ON s.class_id = c.id
    JOIN grades g ON s.grade_id = g.id
    JOIN majors m ON s.major_id = m.id
    WHERE s.name LIKE '%杨卿%'
""").fetchall()
for r in rows:
    print(dict(r))

# Scores with exam name containing 半期 or 下期
print('\n=== 杨卿 scores in 半期/下期 exams ===')
rows = conn.execute("""
    SELECT sc.id, s.name, c.name as class_name, e.name as exam_name, e.exam_date,
           sc.chinese_score, sc.math_score, sc.english_score, sc.professional_score, sc.total_score
    FROM scores sc
    JOIN students s ON sc.student_id = s.id
    JOIN classes c ON s.class_id = c.id
    JOIN exams e ON sc.exam_id = e.id
    WHERE s.name LIKE '%杨卿%' AND (e.name LIKE '%半期%' OR e.name LIKE '%下期%' OR e.name LIKE '%期中%')
""").fetchall()
for r in rows:
    print(dict(r))

# Abnormally large professional_score
print('\n=== Abnormally large professional_score ===')
rows = conn.execute("""
    SELECT sc.id, s.name, sc.professional_score, c.name as class_name, e.name as exam_name
    FROM scores sc
    JOIN students s ON sc.student_id = s.id
    JOIN classes c ON s.class_id = c.id
    JOIN exams e ON sc.exam_id = e.id
    WHERE sc.professional_score > 1000000
""").fetchall()
print([dict(r) for r in rows])

conn.close()
