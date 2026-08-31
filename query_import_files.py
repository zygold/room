import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print('=== Import files related to 半期/下期 ===')
rows = conn.execute("""
    SELECT id, original_filename, validation_status, import_status, exam_id, created_at
    FROM import_files
    WHERE original_filename LIKE '%半期%' OR original_filename LIKE '%下期%'
    ORDER BY id
""").fetchall()
for r in rows:
    print(dict(r))

print('\n=== Recent import files ===')
rows = conn.execute("""
    SELECT id, original_filename, validation_status, import_status, exam_id, created_at
    FROM import_files
    ORDER BY id DESC
    LIMIT 20
""").fetchall()
for r in rows:
    print(dict(r))

conn.close()
