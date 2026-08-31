import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')
import sqlite3
from pathlib import Path
from excel_parser import parse_score_file

# Check file_id=53
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row
file_row = conn.execute('SELECT * FROM import_files WHERE id=53').fetchone()
print('=== file_id=53 ===')
print(dict(file_row))

content = Path(file_row['file_path']).read_bytes()
records = parse_score_file(content, file_row['file_name'])
print(f'\nParsed {len(records)} records')

# Find 周欣怡
for rec in records:
    if rec.get('name') == '周欣怡':
        print('周欣怡 in file_id=53:', rec)
        break
else:
    print('周欣怡 not found in file_id=53')

# Find all 24级电子5班 students
class_name_norm = '24级电子5班（本方）'
print('\n=== 周欣怡 in database ===')
for r in conn.execute('''SELECT st.id, st.name, c.name AS class_name, st.created_at FROM students st JOIN classes c ON st.class_id=c.id WHERE st.name=? AND c.name=?''', ('周欣怡', class_name_norm)).fetchall():
    print(dict(r))

print('\n=== 周欣怡 scores ===')
for r in conn.execute('''SELECT s.*, e.name AS exam_name FROM scores s JOIN exams e ON s.exam_id=e.id WHERE s.student_id=(SELECT id FROM students WHERE name=? AND class_id=(SELECT id FROM classes WHERE name=?)) ORDER BY e.id''', ('周欣怡', class_name_norm)).fetchall():
    print(dict(r))

conn.close()
