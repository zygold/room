import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

# Find top language avg students in 2024级本科方向班
# class_type_id for 本科方向班 is 3? Let's check
print('=== class_types ===')
for r in conn.execute('SELECT * FROM class_types').fetchall():
    print(dict(r))

# Assuming class_type_id=3 is 本科方向班 (本方班)
rows = conn.execute('''
    SELECT st.id, st.name, c.name AS class_name, m.name AS major_name,
           AVG(s.chinese_score + s.math_score + s.english_score) AS language_avg,
           AVG(s.professional_score) AS professional_avg,
           COUNT(s.id) AS exam_count
    FROM students st
    JOIN classes c ON st.class_id=c.id
    JOIN majors m ON st.major_id=m.id
    JOIN grades g ON st.grade_id=g.id
    LEFT JOIN scores s ON s.student_id=st.id
    WHERE g.name='2024级' AND st.class_type_id=3
    GROUP BY st.id
    HAVING exam_count > 0
    ORDER BY language_avg DESC
    LIMIT 20
''').fetchall()

print('\n=== top 20 language avg students ===')
for r in rows:
    d = dict(r)
    d['language_avg'] = round(d['language_avg'], 2) if d['language_avg'] else None
    d['professional_avg'] = round(d['professional_avg'], 2) if d['professional_avg'] else None
    print(d)

# Check the #1 student's scores
if rows:
    top = rows[0]
    print(f"\n=== {top['name']} scores ===")
    for r in conn.execute('''
        SELECT s.*, e.name AS exam_name FROM scores s
        JOIN exams e ON s.exam_id=e.id
        WHERE s.student_id=?
        ORDER BY e.id
    ''', (top['id'],)).fetchall():
        print(dict(r))

conn.close()
