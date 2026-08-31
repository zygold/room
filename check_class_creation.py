import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row
print('=== classes schema ===')
for r in conn.execute("PRAGMA table_info(classes)").fetchall():
    print(dict(r))
print('\n=== classes with 本方 ===')
rows = conn.execute("SELECT * FROM classes WHERE name LIKE '%本方%' ORDER BY name").fetchall()
for r in rows:
    print(dict(r))
conn.close()
