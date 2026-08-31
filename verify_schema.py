import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

print('=== 新表 ===')
for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('class_name_standards', 'class_name_aliases', 'file_subject_mappings', 'scholarship_screen_runs')").fetchall():
    print(r['name'])

print('\n=== students 列 ===')
for r in conn.execute("PRAGMA table_info(students)").fetchall():
    print(r['name'], r['type'])

print('\n=== scores 列 ===')
for r in conn.execute("PRAGMA table_info(scores)").fetchall():
    print(r['name'], r['type'])

print('\n=== scholarships 列 ===')
for r in conn.execute("PRAGMA table_info(scholarships)").fetchall():
    print(r['name'], r['type'])

print('\n=== 外键状态 ===')
for r in conn.execute("PRAGMA foreign_keys").fetchall():
    print(r)

print('\n=== 索引 ===')
for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'").fetchall():
    print(r['name'])

conn.close()
