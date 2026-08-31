import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\scripts')
from merge_duplicate_benfang_classes import merge_scores, merge_scholarships

DB_PATH = r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db'

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

# Find duplicate students in the same class
rows = conn.execute('''
    SELECT class_id, name, COUNT(*) AS cnt, GROUP_CONCAT(id) AS ids
    FROM students
    GROUP BY class_id, name
    HAVING cnt > 1
    ORDER BY cnt DESC
''').fetchall()

print(f'Found {len(rows)} duplicate groups')

total_students = 0
total_scores = 0
total_scholarships = 0

for row in rows:
    class_id = row['class_id']
    name = row['name']
    ids = [int(x) for x in row['ids'].split(',')]
    if len(ids) <= 1:
        continue

    # Keep the first student as target
    target_id = ids[0]
    source_ids = ids[1:]

    for source_id in source_ids:
        total_scores += merge_scores(conn, source_id, target_id)
        total_scholarships += merge_scholarships(conn, source_id, target_id, class_id)
        conn.execute('DELETE FROM students WHERE id=?', (source_id,))
        total_students += 1

# Recalculate student counts
conn.execute('''
    UPDATE classes SET student_count = (SELECT COUNT(*) FROM students WHERE students.class_id = classes.id)
''')
conn.execute('''
    UPDATE grades SET student_count = (SELECT COUNT(*) FROM students WHERE students.grade_id = grades.id)
''')

conn.commit()
print(f'Merged {total_students} duplicate students, {total_scores} scores, {total_scholarships} scholarships')
conn.close()
