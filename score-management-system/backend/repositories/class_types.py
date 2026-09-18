from .base import BaseRepository


class ClassTypeRepository(BaseRepository):
    table = 'class_types'
    pk = 'id'

    def list_with_filters(self, grade_id=None, major_id=None):
        with self.get_connection() as conn:
            if grade_id or major_id:
                sql = 'SELECT DISTINCT ct.* FROM class_types ct JOIN classes c ON c.class_type_id = ct.id WHERE 1=1'
                params = []
                if grade_id:
                    sql += ' AND c.grade_id=?'
                    params.append(grade_id)
                if major_id:
                    sql += ' AND c.major_id=?'
                    params.append(major_id)
                sql += ' ORDER BY id'
            else:
                sql = 'SELECT * FROM class_types ORDER BY id'
                params = []
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def update_active(self, ct_id: int, is_active: int):
        with self.get_connection() as conn:
            conn.execute('UPDATE class_types SET is_active=? WHERE id=?', (is_active, ct_id))
            conn.commit()
