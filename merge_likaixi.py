import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\scripts')
from merge_duplicate_benfang_classes import merge_scores, merge_scholarships
import sqlite3

DB_PATH = r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db'

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

# 李凯茜 two records: 1310 (茶艺), 6857 (旅游1班)
# Merge 1310 into 6857 to keep 24级旅游1班
source_id = 1310
target_id = 6857
target_class_id = conn.execute('SELECT class_id FROM students WHERE id=?', (target_id,)).fetchone()['class_id']

scores_merged = merge_scores(conn, source_id, target_id)
scholarships_merged = merge_scholarships(conn, source_id, target_id, target_class_id)

# Delete source student
conn.execute('DELETE FROM students WHERE id=?', (source_id,))

conn.commit()
print(f'Merged student {source_id} into {target_id}, scores merged: {scores_merged}, scholarships: {scholarships_merged}')

# Show current scores
print('\n=== 李凯茜 current scores ===')
for r in conn.execute('''
    SELECT s.*, e.name AS exam_name FROM scores s
    JOIN exams e ON s.exam_id=e.id
    WHERE s.student_id=?
    ORDER BY e.id
''', (target_id,)).fetchall():
    print(dict(r))

conn.close()
