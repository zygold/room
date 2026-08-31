import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')
import sqlite3
from pathlib import Path
from excel_parser import parse_score_file

conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

# Check all import_files for 李凯茜
files = conn.execute('SELECT * FROM import_files ORDER BY id').fetchall()
for f in files:
    path = Path(f['file_path'])
    if not path.exists():
        continue
    try:
        records = parse_score_file(path.read_bytes(), f['file_name'])
        for rec in records:
            if rec.get('name') == '李凯茜':
                print(f"file_id={f['id']} {f['file_name']} exam_type={f['exam_type']}: class={rec.get('class_name')}, 语文={rec.get('语文')}, 数学={rec.get('数学')}, 英语={rec.get('英语')}, 专业={rec.get('专业课')}")
                break
    except Exception as e:
        print(f"file_id={f['id']} parse error: {e}")

print('\n=== 李凯茜 in database ===')
for r in conn.execute("SELECT st.id, st.name, c.name AS class_name, st.created_at FROM students st JOIN classes c ON st.class_id=c.id WHERE st.name='李凯茜' ORDER BY st.created_at").fetchall():
    print(dict(r))

print('\n=== 李凯茜 scores in database ===')
for r in conn.execute("""
    SELECT s.*, e.name AS exam_name FROM scores s
    JOIN exams e ON s.exam_id=e.id
    WHERE s.student_id IN (SELECT id FROM students WHERE name='李凯茜')
    ORDER BY e.id
""").fetchall():
    print(dict(r))

conn.close()
