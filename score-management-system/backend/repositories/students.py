from .base import BaseRepository


class StudentRepository(BaseRepository):
    table = 'students'
    pk = 'id'

    def list_with_filters(self, class_id=None, grade_id=None, keyword=None):
        with self.get_connection() as conn:
            sql = '''
            SELECT st.*, c.name as class_name, g.name as grade_name, m.name as major_name, ct.name as class_type_name
            FROM students st
            JOIN classes c ON st.class_id = c.id
            JOIN grades g ON st.grade_id = g.id
            JOIN majors m ON st.major_id = m.id
            JOIN class_types ct ON st.class_type_id = ct.id
            WHERE 1=1
            '''
            params = []
            if class_id:
                sql += ' AND st.class_id=?'
                params.append(class_id)
            if grade_id:
                sql += ' AND st.grade_id=?'
                params.append(grade_id)
            if keyword:
                sql += ' AND st.name LIKE ?'
                params.append(f'%{keyword}%')
            sql += ' ORDER BY st.id LIMIT 500'
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def count_homeroom_set(self):
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM students WHERE homeroom_teacher IS NOT NULL AND homeroom_teacher != ''"
            ).fetchone()[0]

    def update_homeroom_by_class_name(self, teacher, class_name, conn=None):
        own_conn = False
        if conn is None:
            conn = self.get_connection()
            own_conn = True
        try:
            cur = conn.execute(
                'UPDATE students SET homeroom_teacher=? WHERE class_id IN (SELECT id FROM classes WHERE name=?)',
                (teacher, class_name),
            )
            return cur.rowcount
        finally:
            if own_conn:
                conn.close()
    def get_by_student_no_and_class(self, student_no, class_id, conn=None):
        cur = self._execute_sql(
            "SELECT id FROM students WHERE student_no=? AND class_id=?",
            (student_no, class_id), conn=conn, commit=False)
        row = cur.fetchone()
        return row["id"] if row else None

    def get_by_name_and_class(self, name, class_id, conn=None):
        cur = self._execute_sql(
            "SELECT id FROM students WHERE name=? AND class_id=?",
            (name, class_id), conn=conn, commit=False)
        return [r["id"] for r in cur.fetchall()]

    def create_student(self, name, student_no, grade_id, major_id, class_type_id, class_id, conn=None):
        from utils.common import now_str
        cur = self._execute_sql(
            """INSERT INTO students (name, student_no, grade_id, major_id, class_type_id,
               class_id, homeroom_teacher, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, student_no, grade_id, major_id, class_type_id, class_id, "", now_str()),
            conn=conn, commit=False)
        return cur.lastrowid



    def update_homeroom_by_class(self, class_id, homeroom_teacher, conn=None):
            self._execute_sql(conn,
                'UPDATE students SET homeroom_teacher = ? WHERE class_id = ?',
                (homeroom_teacher, class_id))
