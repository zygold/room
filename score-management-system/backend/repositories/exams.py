from .base import BaseRepository


class ExamRepository(BaseRepository):
    table = 'exams'
    pk = 'id'

    def list_with_filters(self, school_year=None, semester=None, exam_type=None):
        with self.get_connection() as conn:
            sql = 'SELECT * FROM exams WHERE 1=1'
            params = []
            if school_year:
                sql += ' AND school_year=?'
                params.append(school_year)
            if semester:
                sql += ' AND semester=?'
                params.append(semester)
            if exam_type:
                sql += ' AND exam_type=?'
                params.append(exam_type)
            sql += ' ORDER BY school_year DESC, semester DESC, month DESC, id DESC'
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def delete_cascade(self, exam_id: int) -> tuple:
        with self.get_connection() as conn:
            exam = conn.execute('SELECT id, name FROM exams WHERE id=?', (exam_id,)).fetchone()
            if not exam:
                return None, 0
            score_count = conn.execute('SELECT COUNT(*) FROM scores WHERE exam_id=?', (exam_id,)).fetchone()[0]
            conn.execute('DELETE FROM scores WHERE exam_id=?', (exam_id,))
            conn.execute('DELETE FROM scholarships WHERE exam_id=?', (exam_id,))
            conn.execute('DELETE FROM exams WHERE id=?', (exam_id,))
            conn.commit()
            return exam, score_count


    def list_imported_by_filters(self, school_year=None, semester=None, exam_type=None):
        with self.get_connection() as conn:
            sql = "SELECT id, name, school_year, semester, exam_type, month, exam_date FROM exams WHERE is_imported = 1"
            params = []
            if school_year:
                sql += " AND school_year = ?"
                params.append(school_year)
            if semester:
                sql += " AND semester = ?"
                params.append(semester)
            if exam_type:
                sql += " AND exam_type = ?"
                params.append(exam_type)
            sql += " ORDER BY exam_date DESC, id DESC"
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def mark_imported(self, exam_id, conn=None):
            own_conn = False
            if conn is None:
                conn = self.get_connection()
                own_conn = True
            try:
                conn.execute('UPDATE exams SET is_imported=1 WHERE id=?', (exam_id,))
                conn.commit()
            finally:
                if own_conn:
                    conn.close()

    def find_by_meta(self, name, exam_type, school_year=None, semester=None, month=None, conn=None):
        sql = """SELECT id FROM exams
                 WHERE name=? AND exam_type=? AND IFNULL(school_year, '')=IFNULL(?, '')
                   AND IFNULL(semester, '')=IFNULL(?, '') AND IFNULL(month, '')=IFNULL(?, '')
                 LIMIT 1"""
        params = (name, exam_type, school_year or '', semester or '',
                  month if month is not None else '')
        cur = self._execute_sql(sql, params, conn=conn, commit=False)
        row = cur.fetchone()
        return row["id"] if row else None

    def create_exam(self, name, exam_type, school_year, semester, month, exam_date, conn=None):
        cur = self._execute_sql(
            """INSERT INTO exams (name, exam_type, school_year, semester, month, exam_date, is_imported, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, exam_type, school_year, semester, month, exam_date, 1,
             __import__('utils.common', fromlist=['now_str']).now_str()),
            conn=conn, commit=False)
        return cur.lastrowid

class ExamSubjectConfigRepository(BaseRepository):
    table = 'exam_subject_configs'
    pk = 'id'

    def get_for_exam(self, exam_id: int) -> dict:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT subject_name, max_score FROM exam_subject_configs WHERE exam_id=?',
                (exam_id,),
            ).fetchall()
            return {r['subject_name']: r['max_score'] for r in rows}

    def set_for_exam(self, exam_id: int, configs: dict):
        with self.get_connection() as conn:
            for subject_name, max_score in configs.items():
                conn.execute(
                    '''INSERT INTO exam_subject_configs (exam_id, subject_name, max_score)
                       VALUES (?, ?, ?)
                       ON CONFLICT(exam_id, subject_name) DO UPDATE SET max_score=excluded.max_score''',
                    (exam_id, subject_name, max_score),
                )
            conn.commit()

    def upsert(self, exam_id, subject_name, max_score, conn=None):
        cur = self._execute_sql(
            """INSERT INTO exam_subject_configs (exam_id, subject_name, max_score)
               VALUES (?, ?, ?)
               ON CONFLICT(exam_id, subject_name) DO UPDATE SET max_score=?""",
            (exam_id, subject_name, max_score, max_score),
            conn=conn, commit=False)



    def get_major_id(self, exam_id, conn=None):
            rows = self._execute_sql(conn, 'SELECT major_id FROM exams WHERE id = ?', (exam_id,))
            return rows[0]["major_id"] if rows else None


    def get_subject_configs(self, exam_id, conn=None):
            """Get exam_subject_configs rows for an exam."""
            return self._execute_sql(conn,
                'SELECT subject_name, max_score FROM exam_subject_configs WHERE exam_id=?',
                (exam_id,))
