import sqlite3

conn = sqlite3.connect(r'h:\DAIMA\CJjiangxuej\score-management-system\data\score_management.db')
conn.row_factory = sqlite3.Row

print('=== 杨璐瑜学生信息 ===')
rows = conn.execute("SELECT * FROM students WHERE name='杨璐瑜'").fetchall()
for r in rows:
    print(dict(r))

print('\n=== 杨璐瑜成绩 ===')
for r in rows:
    stu_id = r['id']
    scores = conn.execute('''SELECT s.*, e.name as exam_name, e.school_year, e.semester, e.exam_type, e.month
        FROM scores s
        JOIN exams e ON s.exam_id=e.id
        WHERE s.student_id=?
        ORDER BY e.id''', (stu_id,)).fetchall()
    for sc in scores:
        print(dict(sc))

print('\n=== 考试列表 ===')
exams = conn.execute('SELECT * FROM exams').fetchall()
for e in exams:
    print(dict(e))

conn.close()
