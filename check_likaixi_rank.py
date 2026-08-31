import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

# 旅游服务与管理专业所有2024级升学实验班学生的专业平均分
rows = conn.execute('''
    SELECT st.id, st.name, c.name AS class_name,
           AVG(s.professional_score) AS professional_avg,
           AVG(s.chinese_score + s.math_score + s.english_score) AS language_avg
    FROM students st
    JOIN classes c ON st.class_id=c.id
    JOIN majors m ON st.major_id=m.id
    JOIN grades g ON st.grade_id=g.id
    LEFT JOIN scores s ON s.student_id=st.id
    WHERE g.name='2024级' AND st.class_type_id=1 AND m.name='旅游服务与管理'
    GROUP BY st.id
    ORDER BY professional_avg DESC
''').fetchall()

print('=== 旅游服务与管理专业 升学实验班 专业平均排名 ===')
for idx, r in enumerate(rows, 1):
    avg = r['professional_avg']
    lang = r['language_avg']
    print(f'{idx}: {r["name"]} {r["class_name"]} 专业平均={round(avg,2) if avg else None} 语数外平均={round(lang,2) if lang else None}')

conn.close()
