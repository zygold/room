import sqlite3
conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row
print('=== class 184 ===')
for r in conn.execute('SELECT * FROM classes WHERE id=184').fetchall():
    print(dict(r))
print('=== class 191 ===')
for r in conn.execute('SELECT * FROM classes WHERE id=191').fetchall():
    print(dict(r))
print('=== 杨璐瑜同班学生期末成绩专业为空数量 ===')
for cls_id in [184, 191]:
    rows = conn.execute('''SELECT COUNT(*) FROM scores s JOIN students st ON s.student_id=st.id 
        WHERE st.class_id=? AND s.exam_id=26 AND s.professional_score IS NULL''', (cls_id,)).fetchall()
    print(f'class {cls_id} final exam prof null: {rows[0][0]}')
print('=== 10月月考 professional_score 非空数量 ===')
for cls_id in [184, 191]:
    rows = conn.execute('''SELECT COUNT(*) FROM scores s JOIN students st ON s.student_id=st.id 
        WHERE st.class_id=? AND s.exam_id=24 AND s.professional_score IS NOT NULL''', (cls_id,)).fetchall()
    print(f'class {cls_id} monthly prof not null: {rows[0][0]}')
conn.close()
