from .base import BaseRepository
from utils.common import now_str


class MajorRepository(BaseRepository):
    table = 'majors'
    pk = 'id'

    def list_with_optional_grade(self, grade_id=None):
        with self.get_connection() as conn:
            if grade_id:
                rows = conn.execute(
                    'SELECT DISTINCT m.* FROM majors m JOIN classes c ON c.major_id = m.id WHERE c.grade_id = ? ORDER BY m.id',
                    (grade_id,),
                ).fetchall()
            else:
                rows = conn.execute('SELECT * FROM majors ORDER BY id').fetchall()
            return [dict(r) for r in rows]

    def create(self, name: str) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                'INSERT INTO majors (name, created_at) VALUES (?, ?)',
                (name, now_str()),
            )
            major_id = cur.lastrowid
            conn.execute(
                'INSERT OR IGNORE INTO subject_standards (subject_name, major_id, max_score, pass_score, is_fixed) VALUES (?, ?, 100, 60, 0)',
                ('专业课', major_id),
            )
            conn.commit()
            return major_id

    def update(self, major_id: int, name: str):
        with self.get_connection() as conn:
            conn.execute('UPDATE majors SET name=? WHERE id=?', (name, major_id))
            conn.commit()

    def delete_cascade(self, major_id: int):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM students WHERE major_id=?', (major_id,))
            conn.execute('DELETE FROM classes WHERE major_id=?', (major_id,))
            conn.execute('DELETE FROM majors WHERE id=?', (major_id,))
            conn.commit()
