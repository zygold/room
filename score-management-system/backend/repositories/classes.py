from .base import BaseRepository
from utils.common import now_str


class ClassRepository(BaseRepository):
    table = 'classes'
    pk = 'id'

    # --- 基础 CRUD ---
    def create(self, name, grade_id, major_id, class_type_id) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                'INSERT INTO classes (name, grade_id, major_id, class_type_id) VALUES (?, ?, ?, ?)',
                (name, grade_id, major_id, class_type_id),
            )
            conn.commit()
            return cur.lastrowid

    def update_basic(self, class_id, name, grade_id, major_id, class_type_id):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE classes SET name=?, grade_id=?, major_id=?, class_type_id=? WHERE id=?',
                (name, grade_id, major_id, class_type_id, class_id),
            )
            conn.commit()

    def delete_cascade(self, class_id):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM students WHERE class_id=?', (class_id,))
            conn.execute('DELETE FROM classes WHERE id=?', (class_id,))
            conn.commit()

    # --- JOIN 查询 (settings/classes/list_classes) ---
    def list_with_filters_joined(self, grade_id=None, major_id=None, class_type_id=None):
        with self.get_connection() as conn:
            sql = '''
            SELECT c.*, g.name as grade_name, m.name as major_name, ct.name as class_type_name
            FROM classes c
            JOIN grades g ON c.grade_id = g.id
            JOIN majors m ON c.major_id = m.id
            JOIN class_types ct ON c.class_type_id = ct.id
            WHERE 1=1
            '''
            params = []
            if grade_id: sql += ' AND c.grade_id=?'; params.append(grade_id)
            if major_id: sql += ' AND c.major_id=?'; params.append(major_id)
            if class_type_id: sql += ' AND c.class_type_id=?'; params.append(class_type_id)
            sql += ' ORDER BY c.id'
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # --- timetable 专用 ---
    def find_by_name_with_variants(self, normalized_name):
        with self.get_connection() as conn:
            for candidate in [normalized_name]:
                row = conn.execute(
                    'SELECT id, grade_id, major_id, class_type_id FROM classes WHERE name=?',
                    (candidate,),
                ).fetchone()
                if row:
                    return dict(row)
                alt = normalized_name.rstrip('（本方）')
                if alt != normalized_name:
                    row = conn.execute(
                        'SELECT id, grade_id, major_id, class_type_id FROM classes WHERE name=?',
                        (alt,),
                    ).fetchone()
                    if row:
                        return dict(row)
                alt2 = normalized_name + '（本方）'
                row = conn.execute(
                    'SELECT id, grade_id, major_id, class_type_id FROM classes WHERE name=?',
                    (alt2,),
                ).fetchone()
                if row:
                    return dict(row)
            return None

    def find_by_name(self, name):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM classes WHERE name=?', (name,)).fetchone()
            return dict(row) if row else None

    def find_id_by_name(self, name):
        with self.get_connection() as conn:
            row = conn.execute('SELECT id FROM classes WHERE name=?', (name,)).fetchone()
            return row[0] if row else None

    # --- headteacher 专用 ---
    def update_head_teacher(self, class_id, head_teacher):
        with self.get_connection() as conn:
            conn.execute('UPDATE classes SET head_teacher=? WHERE id=?', (head_teacher, class_id))
            conn.commit()

    def update_students_homeroom(self, class_id, homeroom):
        with self.get_connection() as conn:
            conn.execute('UPDATE students SET homeroom_teacher=? WHERE class_id=?', (homeroom, class_id))
            conn.commit()

    def has_head_teacher_column(self):
        with self.get_connection() as conn:
            cols = [r[1] for r in conn.execute('PRAGMA table_info(classes)').fetchall()]
            return 'head_teacher' in cols

    def overview(self):
        with self.get_connection() as conn:
            total = conn.execute('SELECT COUNT(*) FROM classes').fetchone()[0]
            with_ht = conn.execute("SELECT COUNT(*) FROM classes WHERE head_teacher IS NOT NULL AND head_teacher != ''").fetchone()[0]
            sample = [dict(r) for r in conn.execute("SELECT name, head_teacher FROM classes WHERE head_teacher IS NOT NULL AND head_teacher != '' LIMIT 10").fetchall()]
            need = [dict(r) for r in conn.execute("SELECT id, name FROM classes WHERE head_teacher IS NULL OR head_teacher = '' LIMIT 20").fetchall()]
        return {'total_classes': total, 'with_head_teacher': with_ht,
                'coverage_pct': round(with_ht / total * 100, 1) if total else 0,
                'sample': sample, 'need_fill': need}

    def get_ids_with_head_teacher(self):
        with self.get_connection() as conn:
            return {r['id'] for r in conn.execute("SELECT id FROM classes WHERE head_teacher IS NOT NULL AND head_teacher != ''").fetchall()}

    def batch_get_by_ids(self, ids):
        if not ids: return []
        with self.get_connection() as conn:
            placeholders = ','.join(['?'] * len(ids))
            return [dict(r) for r in conn.execute(
                f'SELECT id, name, head_teacher FROM classes WHERE id IN ({placeholders})', tuple(ids)
            ).fetchall()]

    def batch_get_homeroom_from_students(self, class_ids):
        if not class_ids: return {}
        with self.get_connection() as conn:
            ph = ','.join(['?'] * len(class_ids))
            rows = conn.execute(
                f"SELECT class_id, homeroom_teacher FROM students WHERE class_id IN ({ph}) AND homeroom_teacher IS NOT NULL AND homeroom_teacher != '' GROUP BY class_id",
                tuple(class_ids),
            ).fetchall()
            return {r['class_id']: r['homeroom_teacher'] for r in rows}
    def get_by_name(self, name, conn=None):
        return self.query_one(
            "SELECT id, grade_id, major_id, class_type_id FROM classes WHERE name=?",
            (name,), conn=conn)

    def get_by_id_detailed(self, class_id, conn=None):
        return self.query_one(
            "SELECT id, grade_id, major_id, class_type_id FROM classes WHERE id=?",
            (class_id,), conn=conn)

    # --- Phase 3+ 新增 ---
    def list_basic(self, conn=None):
        """Return [(id, name), ...] - 轻量列表."""
        rows = self.query('SELECT id, name FROM classes', conn=conn)
        return [(r["id"], r["name"]) for r in rows]

    def update_head_teacher_batch(self, class_id, head_teacher, conn=None):
        """Update a single class's head teacher."""
        self.execute_dml('UPDATE classes SET head_teacher = ? WHERE id = ?',
                         (head_teacher, class_id), conn=conn, commit=False)
