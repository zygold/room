import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row
print('=== 期末考试有文化课但无专业课的学生 ===')
rows = conn.execute('''
    SELECT e.name AS exam_name, c.name AS class_name, COUNT(*) AS cnt
    FROM scores s
    JOIN students st ON s.student_id=st.id
    JOIN classes c ON st.class_id=c.id
    JOIN exams e ON s.exam_id=e.id
    WHERE e.exam_type="期末考试" AND s.chinese_score IS NOT NULL AND s.professional_score IS NULL
    GROUP BY e.name, c.name
    ORDER BY e.name, c.name
''').fetchall()
for r in rows:
    print(dict(r))

print('\n=== 期末考试专业课成绩统计 ===')
rows = conn.execute('''
    SELECT e.name AS exam_name, COUNT(*) AS total, SUM(CASE WHEN s.professional_score IS NOT NULL THEN 1 ELSE 0 END) AS has_prof
    FROM scores s
    JOIN exams e ON s.exam_id=e.id
    WHERE e.exam_type="期末考试"
    GROUP BY e.name
''').fetchall()
for r in rows:
    print(dict(r))
conn.close()
