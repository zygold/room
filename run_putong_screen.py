import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')

import sqlite3
from database import get_db
from services.scholarship_engine import run_screen

g = get_db()
conn = g.__enter__()
grade = conn.execute("SELECT id FROM grades WHERE name='2024级'").fetchone()
class_type = conn.execute("SELECT id FROM class_types WHERE name='升学实验班'").fetchone()
exams = conn.execute("SELECT id FROM exams ORDER BY id").fetchall()
conn.close()
g.__exit__(None, None, None)

count = run_screen(
    grade_id=grade['id'],
    class_type_ids=[class_type['id']],
    exam_ids=[e['id'] for e in exams],
    category='普通升学班',
    name='2024级普通升学班奖学金评定'
)
print('winners count:', count)

conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT st.name, c.name AS class_name, m.name AS major_name, s.average_score, s.language_avg, s.professional_avg,
           s.grade_rank, s.major_rank, s.award_level
    FROM scholarships s
    JOIN students st ON s.student_id=st.id
    JOIN classes c ON st.class_id=c.id
    JOIN majors m ON st.major_id=m.id
    WHERE s.exam_id=?
    ORDER BY s.award_level, s.average_score DESC
''', (exams[0]['id'],)).fetchall()
print('\n=== scholarship results ===')
for r in rows:
    print(dict(r))
conn.close()
