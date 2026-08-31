import sys
sys.path.insert(0, 'score-management-system/backend')
from database import get_db
from routers.import_scores import _import_records_into_exam

with get_db(autocommit=False) as conn:
    # 找一个已有成绩的学生
    row = conn.execute('''
        SELECT s.id, s.student_id, st.name, st.class_id, c.name as class_name
        FROM scores s
        JOIN students st ON s.student_id=st.id
        JOIN classes c ON st.class_id=c.id
        WHERE s.exam_id IN (SELECT id FROM exams ORDER BY id DESC LIMIT 1)
        LIMIT 1
    ''').fetchone()
    if not row:
        print('No existing score for exam 26')
    else:
        print('Existing:', row['name'], row['class_name'])
        records = [{
            'name': row['name'],
            'class_name': row['class_name'],
            'row_index': 1,
            '语文': 999,
            '数学': 999,
            '英语': 999,
            '专业课': 999,
        }]
        # First try without overwrite - should raise conflict
        try:
            _import_records_into_exam(conn, records, 26, 'test_overwrite', 1, 1)
            print('ERROR: should have raised conflict')
        except Exception as e:
            print('Conflict raised (expected):', type(e).__name__)
        conn.rollback()

        # Then try with overwrite
        inserted, updated = _import_records_into_exam(conn, records, 26, 'test_overwrite', 1, 1, overwrite_existing=True)
        print('With overwrite - Inserted:', inserted, 'Updated:', updated)
    conn.rollback()
