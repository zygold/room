import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

# 24级电子5班（本方）所有学生的 professional_avg
rows = conn.execute('''
    SELECT st.id, st.name,
           AVG(s.professional_score) AS professional_avg
    FROM students st
    LEFT JOIN scores s ON s.student_id=st.id
    WHERE st.class_id=(SELECT id FROM classes WHERE name='24级电子5班（本方）')
    GROUP BY st.id
    ORDER BY professional_avg DESC
''').fetchall()

print('=== 24级电子5班（本方）专业平均排名 ===')
for idx, r in enumerate(rows, 1):
    avg = r['professional_avg']
    print(f'{idx}: {r["name"]} {round(avg, 2) if avg else None}')

conn.close()
