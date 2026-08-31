import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')
import sqlite3
from excel_parser import normalize_class_name

conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

classes = conn.execute('SELECT id, name FROM classes').fetchall()
groups = {}
for c in classes:
    norm = normalize_class_name(c['name'])
    key = (c['id'], norm)  # use id to avoid false grouping
    # Actually group by normalized name only
    groups.setdefault(norm, []).append(c)

print('=== duplicate classes by normalized name ===')
for norm, items in sorted(groups.items()):
    if len(items) > 1:
        print(norm, '->', [c['name'] for c in items])

print('\n=== total classes ===', len(classes))
print('\n=== sample classes ===')
for r in sorted(classes, key=lambda x: x['name'])[:20]:
    print(r['name'])
conn.close()
