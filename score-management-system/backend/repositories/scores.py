from .base import BaseRepository


class ScoreRepository(BaseRepository):
    table = 'scores'
    pk = 'id'

    SORT_FIELD_MAP = {
        'name': 'st.name', 'student_no': 'st.student_no',
        'grade_name': 'g.name', 'major_name': 'm.name',
        'class_type_name': 'ct.name', 'class_name': 'c.name',
        'exam_name': 'e.name', 'chinese_score': 's.chinese_score',
        'math_score': 's.math_score', 'english_score': 's.english_score',
        'professional_score': 's.professional_score', 'total_score': 's.total_score',
        'is_converted': 's.is_converted',
    }

    def _base_join(self):
        return '''
        FROM scores s
        JOIN students st ON s.student_id = st.id
        JOIN classes c ON st.class_id = c.id
        JOIN grades g ON st.grade_id = g.id
        JOIN majors m ON st.major_id = m.id
        JOIN class_types ct ON st.class_type_id = ct.id
        JOIN exams e ON s.exam_id = e.id
        WHERE 1=1
        '''

    def list_with_filters(self, grade_id=None, major_id=None, class_type_id=None,
                          class_id=None, exam_id=None, exam_type=None,
                          school_year=None, semester=None, month=None,
                          keyword=None, is_converted=None, sort_field=None,
                          sort_order='desc', page=1, page_size=100):
        with self.get_connection() as conn:
            sql = '''
            SELECT s.*, st.name as student_name, st.student_no, st.homeroom_teacher,
                   c.name as class_name, g.name as grade_name, m.name as major_name, ct.name as class_type_name,
                   e.name as exam_name, e.exam_type, e.exam_date, e.school_year, e.semester, e.month
            ''' + self._base_join()
            params = []
            if grade_id: sql += ' AND st.grade_id=?'; params.append(grade_id)
            if major_id: sql += ' AND st.major_id=?'; params.append(major_id)
            if class_type_id: sql += ' AND st.class_type_id=?'; params.append(class_type_id)
            if class_id: sql += ' AND st.class_id=?'; params.append(class_id)
            if exam_id: sql += ' AND s.exam_id=?'; params.append(exam_id)
            if exam_type: sql += ' AND e.exam_type=?'; params.append(exam_type)
            if school_year: sql += ' AND e.school_year=?'; params.append(school_year)
            if semester: sql += ' AND e.semester=?'; params.append(semester)
            if month is not None: sql += ' AND e.month=?'; params.append(month)
            if is_converted is not None: sql += ' AND s.is_converted=?'; params.append(is_converted)
            if keyword: sql += ' AND st.name LIKE ?'; params.append(f'%{keyword}%')

            count_sql = f'SELECT COUNT(*) FROM ({sql})'
            total = conn.execute(count_sql, params).fetchone()[0]

            order_col = self.SORT_FIELD_MAP.get(sort_field, 's.id')
            order_dir = 'ASC' if sort_order and sort_order.lower() == 'asc' else 'DESC'
            sql += f' ORDER BY {order_col} {order_dir}, s.id DESC LIMIT ? OFFSET ?'
            params.extend([page_size, (page - 1) * page_size])
            rows = conn.execute(sql, params).fetchall()
            return {'total': total, 'page': page, 'page_size': page_size, 'items': [dict(r) for r in rows]}

    def get_by_id(self, score_id: int):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM scores WHERE id=?', (score_id,)).fetchone()
            return dict(row) if row else None

    def update(self, score_id: int, updates: list, values: list):
        with self.get_connection() as conn:
            conn.execute(
                f"UPDATE scores SET {', '.join(updates)} WHERE id=?",
                values + [score_id],
            )
            conn.commit()

    def delete_by_ids(self, ids: list) -> int:
        if not ids:
            return 0
        with self.get_connection() as conn:
            deleted = 0
            chunk_size = 500
            for i in range(0, len(ids), chunk_size):
                chunk = ids[i:i + chunk_size]
                placeholders = ','.join(['?'] * len(chunk))
                cur = conn.execute(f'DELETE FROM scores WHERE id IN ({placeholders})', chunk)
                deleted += cur.rowcount
            conn.commit()
            return deleted

    def delete_by_filter_ids(self, grade_id=None, major_id=None, class_type_id=None,
                             class_id=None, exam_id=None, exam_type=None,
                             school_year=None, semester=None, month=None,
                             keyword=None, is_converted=None) -> int:
        with self.get_connection() as conn:
            sql = 'SELECT s.id FROM scores s' + self._base_join()
            params = []
            if grade_id: sql += ' AND st.grade_id=?'; params.append(grade_id)
            if major_id: sql += ' AND st.major_id=?'; params.append(major_id)
            if class_type_id: sql += ' AND st.class_type_id=?'; params.append(class_type_id)
            if class_id: sql += ' AND st.class_id=?'; params.append(class_id)
            if exam_id: sql += ' AND s.exam_id=?'; params.append(exam_id)
            if exam_type: sql += ' AND e.exam_type=?'; params.append(exam_type)
            if school_year: sql += ' AND e.school_year=?'; params.append(school_year)
            if semester: sql += ' AND e.semester=?'; params.append(semester)
            if month is not None: sql += ' AND e.month=?'; params.append(month)
            if is_converted is not None: sql += ' AND s.is_converted=?'; params.append(is_converted)
            if keyword: sql += ' AND st.name LIKE ?'; params.append(f'%{keyword}%')
            ids = [r[0] for r in conn.execute(sql, params).fetchall()]
            return self.delete_by_ids(ids)

    def get_subject_details(self, score_ids: list) -> dict:
        if not score_ids:
            return {}
        with self.get_connection() as conn:
            placeholders = ','.join(['?'] * len(score_ids))
            rows = conn.execute(
                f'''SELECT score_id, subject_name, original_score, converted_score
                    FROM score_subject_details
                    WHERE score_id IN ({placeholders})
                    ORDER BY score_id, subject_name''',
                list(score_ids),
            ).fetchall()
        result = {}
        for r in rows:
            result.setdefault(r['score_id'], []).append({
                'subject_name': r['subject_name'],
                'original_score': r['original_score'],
                'converted_score': r['converted_score'],
            })
        return result
    def get_by_student_and_exam(self, student_id, exam_id, conn=None):
        cur = self._execute_sql(
            """SELECT id, chinese_score, math_score, english_score, professional_score,
                      physics_score, chemistry_score, biology_score, history_score,
                      geography_score, politics_score, total_score
               FROM scores WHERE student_id=? AND exam_id=?""",
            (student_id, exam_id), conn=conn, commit=False)
        return cur.fetchone()

    def check_students_participated(self, exam_id, student_ids, conn=None):
        if not student_ids:
            return set()
        ph = ",".join(["?"] * len(student_ids))
        cur = self._execute_sql(
            f"SELECT student_id FROM scores WHERE exam_id=? AND student_id IN ({ph})",
            (exam_id,) + tuple(student_ids), conn=conn, commit=False)
        return {r["student_id"] for r in cur.fetchall()}

    def update_scores(self, student_id, exam_id, fields_values, conn=None):
        cols = list(fields_values.keys())
        placeholders = ",".join(f"{c}=?" for c in cols)
        values = [fields_values[c] for c in cols] + [student_id, exam_id]
        cur = self._execute_sql(
            f"UPDATE scores SET {placeholders} WHERE student_id=? AND exam_id=?",
            values, conn=conn, commit=False)
        return cur.rowcount

    def insert_score(self, student_id, exam_id, scores_dict, total_score, prof_max_score, batch, conn=None):
        from utils.common import now_str
        cur = self._execute_sql(
            """INSERT INTO scores
               (student_id, exam_id, chinese_score, math_score, english_score,
                physics_score, chemistry_score, biology_score, history_score,
                geography_score, politics_score, professional_score,
                total_score, professional_max_score, is_converted, import_batch, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (student_id, exam_id,
             scores_dict.get("chinese_score"),
             scores_dict.get("math_score"),
             scores_dict.get("english_score"),
             scores_dict.get("physics_score"),
             scores_dict.get("chemistry_score"),
             scores_dict.get("biology_score"),
             scores_dict.get("history_score"),
             scores_dict.get("geography_score"),
             scores_dict.get("politics_score"),
             scores_dict.get("professional_score"),
             total_score, prof_max_score, 0, batch, now_str()),
            conn=conn, commit=False)
        return cur.lastrowid



    def update_converted(self, score_id, chinese_c, math_c, english_c, prof_c, total_c, prof_max, conn=None):
            self._execute_sql(conn,
                """UPDATE scores SET
                   chinese_converted=?, math_converted=?, english_converted=?, professional_converted=?,
                   professional_max_score=?, total_converted=?, is_converted=1
                   WHERE id=?""",
                (chinese_c, math_c, english_c, prof_c, prof_max, total_c, score_id))
