import sqlite3

conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

print('=== import_files ===')
rows = conn.execute('SELECT * FROM import_files ORDER BY id').fetchall()
for r in rows:
    print(dict(r))

conn.close()
