import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Insert default professional subject standards for majors that don't have one.
conn.execute("""
    INSERT INTO subject_standards (subject_name, major_id, max_score, pass_score, is_fixed)
    SELECT '专业课', m.id, 100, 60, 0
    FROM majors m
    LEFT JOIN subject_standards s ON s.major_id = m.id AND s.subject_name = '专业课'
    WHERE s.id IS NULL
""")
conn.commit()

print('Inserted default professional standards for majors without one.')

# Verify
rows = conn.execute("SELECT m.id, m.name, s.max_score, s.pass_score FROM majors m LEFT JOIN subject_standards s ON s.major_id = m.id AND s.subject_name = '专业课' ORDER BY m.id").fetchall()
for r in rows:
    print(r['id'], r['name'], r['max_score'], r['pass_score'])

conn.close()
