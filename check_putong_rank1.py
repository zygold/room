import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

# 2024级升学实验班（普通升学班）语数外平均分前10
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
    WHERE g.name='2024级' AND st.class_type_id=1
    GROUP BY st.id
    HAVING exam_count > 0
    ORDER BY language_avg DESC
    LIMIT 15
''').fetchall()

print('=== 2024级升学实验班语数外平均分前15 ===')
for r in rows:
    d = dict(r)
    d['language_avg'] = round(d['language_avg'], 2) if d['language_avg'] else None
    d['professional_avg'] = round(d['professional_avg'], 2) if d['professional_avg'] else None
    print(d)

if rows:
    top = rows[0]
    print(f"\n=== {top['name']} 成绩 ===")
    for r in conn.execute('''
        SELECT s.*, e.name AS exam_name FROM scores s
        JOIN exams e ON s.exam_id=e.id
        WHERE s.student_id=?
        ORDER BY e.id
    ''', (top['id'],)).fetchall():
        print(dict(r))

conn.close()
