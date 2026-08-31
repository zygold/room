import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')

import sqlite3
from pathlib import Path
from excel_parser import parse_score_file, normalize_class_name

DB_PATH = r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db'
FILE_ID = 55
EXAM_ID = 26

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

file_row = conn.execute('SELECT * FROM import_files WHERE id=?', (FILE_ID,)).fetchone()
if not file_row:
    print(f'File {FILE_ID} not found')
    sys.exit(1)

content = Path(file_row['file_path']).read_bytes()
records = parse_score_file(content, file_row['file_name'])
print(f'Parsed {len(records)} records from file_id={FILE_ID}')

updated = 0
missing_student = 0
multiple_student = 0
no_culture_score = 0

for rec in records:
    name = rec['name']
    class_name = normalize_class_name(rec.get('class_name', ''))
    prof_score = rec.get('专业课')
    if not name or prof_score is None:
        continue

    # Find student by name + class
    students = conn.execute(
        'SELECT st.id FROM students st JOIN classes c ON st.class_id=c.id WHERE st.name=? AND c.name=?',
        (name, class_name)
    ).fetchall()

    if len(students) == 0:
        # Try fallback: class without 本方
        fallback_class = class_name.replace('（本方）', '').replace('(本方)', '')
        students = conn.execute(
            'SELECT st.id FROM students st JOIN classes c ON st.class_id=c.id WHERE st.name=? AND c.name=?',
            (name, fallback_class)
        ).fetchall()

    if len(students) == 0:
        missing_student += 1
        if missing_student <= 5:
            print(f'Missing student: {name} {class_name}')
        continue
    if len(students) > 1:
        multiple_student += 1
        if multiple_student <= 5:
            print(f'Multiple students: {name} {class_name} -> {len(students)}')
        continue

    student_id = students[0]['id']

    # Find existing culture score for exam 26
    score_row = conn.execute(
        'SELECT id, chinese_score, math_score, english_score, professional_score, total_score FROM scores WHERE student_id=? AND exam_id=?',
        (student_id, EXAM_ID)
    ).fetchone()

    if not score_row:
        no_culture_score += 1
        if no_culture_score <= 5:
            print(f'No culture score for: {name} {class_name}')
        continue

    # Merge professional score
    new_prof = float(prof_score)
    total = (score_row['chinese_score'] or 0) + (score_row['math_score'] or 0) + (score_row['english_score'] or 0) + new_prof

    conn.execute(
        '''UPDATE scores SET professional_score=?, professional_max_score=?, total_score=? WHERE id=?''',
        (new_prof, 200.0, total, score_row['id'])
    )
    updated += 1

conn.commit()
print(f'Updated: {updated}, Missing student: {missing_student}, Multiple students: {multiple_student}, No culture score: {no_culture_score}')
conn.close()
