import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')
from excel_parser import normalize_class_name

DB_PATH = r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db'
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 1. Clear professional scores for all 运动训练班 students in all exams
sports_students = conn.execute("""
    SELECT st.id FROM students st
    JOIN classes c ON st.class_id=c.id
    WHERE c.name LIKE '%运动训练%'
""").fetchall()
print(f'Found {len(sports_students)} 运动训练 students')

cleared = 0
for stu in sports_students:
    scores = conn.execute('SELECT id, chinese_score, math_score, english_score FROM scores WHERE student_id=? AND professional_score IS NOT NULL', (stu['id'],)).fetchall()
    for sc in scores:
        total = (sc['chinese_score'] or 0) + (sc['math_score'] or 0) + (sc['english_score'] or 0)
        conn.execute('''
            UPDATE scores SET professional_score=NULL, professional_max_score=NULL, total_score=? WHERE id=?
        ''', (total, sc['id']))
        cleared += 1

print(f'Cleared {cleared} professional scores for 运动训练 students')

# 2. Restore 李凯茜 midterm professional score from file_id=53
from pathlib import Path
file_row = conn.execute('SELECT * FROM import_files WHERE id=53').fetchone()
from excel_parser import parse_score_file
records = parse_score_file(Path(file_row['file_path']).read_bytes(), file_row['file_name'])

restored = 0
for rec in records:
    if rec.get('name') == '李凯茜' and rec.get('class_name') == '24级旅游1班':
        prof = rec.get('专业课')
        if prof is None:
            continue
        # 李凯茜 now has only student_id=6857
        score_row = conn.execute('''
            SELECT id, chinese_score, math_score, english_score FROM scores
            WHERE student_id=(SELECT id FROM students WHERE name='李凯茜' LIMIT 1) AND exam_id=25
        ''').fetchone()
        if score_row:
            total = (score_row['chinese_score'] or 0) + (score_row['math_score'] or 0) + (score_row['english_score'] or 0) + float(prof)
            conn.execute('''
                UPDATE scores SET professional_score=?, professional_max_score=?, total_score=? WHERE id=?
            ''', (float(prof), 300.0, total, score_row['id']))
            restored += 1
            print(f'Restored 李凯茜 midterm prof_score={prof}, total={total}')
        break

conn.commit()
print(f'Restored {restored} 李凯茜 score')
conn.close()
