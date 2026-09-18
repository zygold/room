from .base import BaseRepository
from utils.common import now_str


class GradeRepository(BaseRepository):
    table = 'grades'
    pk = 'id'

    def create(self, name: str, status: str = '在读') -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                'INSERT INTO grades (name, status, created_at) VALUES (?, ?, ?)',
                (name, status, now_str()),
            )
            conn.commit()
            return cur.lastrowid

    def update(self, grade_id: int, name: str, status: str):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE grades SET name=?, status=? WHERE id=?',
                (name, status, grade_id),
            )
            conn.commit()

    def delete_cascade(self, grade_id: int):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM students WHERE grade_id=?', (grade_id,))
            conn.execute('DELETE FROM classes WHERE grade_id=?', (grade_id,))
            conn.execute('DELETE FROM grades WHERE id=?', (grade_id,))
            conn.commit()
