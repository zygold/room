from .base import BaseRepository


class SubjectStandardRepository(BaseRepository):
    table = 'subject_standards'
    pk = 'id'
    STANDARD_NAMES = ('语文', '数学', '英语', '专业课')

    def list_with_major(self, major_id=None):
        with self.get_connection() as conn:
            sql = '''
            SELECT s.*, m.name as major_name
            FROM subject_standards s
            LEFT JOIN majors m ON s.major_id = m.id
            WHERE s.subject_name IN (?, ?, ?, ?)
            '''
            params = list(self.STANDARD_NAMES)
            if major_id is not None:
                sql += ' AND (s.major_id IS NULL OR s.major_id = ?)'
                params.append(major_id)
            sql += ' ORDER BY s.is_fixed DESC, s.subject_name, s.major_id'
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def update(self, std_id: int, max_score: float, pass_score: float, is_fixed=None):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM subject_standards WHERE id=?', (std_id,)).fetchone()
            if not row:
                return False
            fixed_val = is_fixed if is_fixed is not None else row['is_fixed']
            conn.execute(
                'UPDATE subject_standards SET max_score=?, pass_score=?, is_fixed=? WHERE id=?',
                (max_score, pass_score, fixed_val, std_id),
            )
            conn.commit()
            return True
    def list_all_rows(self, conn=None):
        return self.query(
            "SELECT subject_name, major_id, max_score, pass_score FROM subject_standards",
            conn=conn)

