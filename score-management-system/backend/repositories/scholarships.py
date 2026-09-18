import json
from .base import BaseRepository
from utils.common import now_str


class ScholarshipRuleRepository(BaseRepository):
    table = 'scholarship_rules'
    pk = 'id'

    def list_all(self) -> list:
        return self.get_all()

    def create(self, name: str, conditions: dict, grade_ids: list, class_type_ids: list, is_active: bool = True) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                'INSERT INTO scholarship_rules (name, conditions, grade_ids, class_type_ids, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (name, json.dumps(conditions, ensure_ascii=False), ','.join(map(str, grade_ids)),
                 ','.join(map(str, class_type_ids)), 1 if is_active else 0, now_str()),
            )
            conn.commit()
            return cur.lastrowid

    def update(self, rule_id: int, name: str, conditions: dict, grade_ids: list, class_type_ids: list, is_active: bool = True):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE scholarship_rules SET name=?, conditions=?, grade_ids=?, class_type_ids=?, is_active=? WHERE id=?',
                (name, json.dumps(conditions, ensure_ascii=False), ','.join(map(str, grade_ids)),
                 ','.join(map(str, class_type_ids)), 1 if is_active else 0, rule_id),
            )
            conn.commit()


class ScholarshipCandidateRepository(BaseRepository):
    table = 'scholarships'
    pk = 'id'

    def list_with_filters(self, exam_id=None, class_id=None, review_status=None,
                          award_level=None, grade_id=None, class_type_ids=None,
                          page=1, page_size=20):
        with self.get_connection() as conn:
            sql = '''
            SELECT sch.*, st.name as student_name, st.class_id,
                   c.name as class_name, g.name as grade_name,
                   m.name as major_name, ct.name as class_type_name, e.name as exam_name
            FROM scholarships sch
            JOIN students st ON sch.student_id=st.id
            JOIN classes c ON sch.class_id=c.id
            JOIN grades g ON st.grade_id=g.id
            JOIN majors m ON st.major_id=m.id
            JOIN class_types ct ON st.class_type_id=ct.id
            JOIN exams e ON sch.exam_id=e.id
            WHERE 1=1
            '''
            params = []
            if exam_id: sql += ' AND sch.exam_id=?'; params.append(exam_id)
            if class_id: sql += ' AND sch.class_id=?'; params.append(class_id)
            if review_status: sql += ' AND sch.review_status=?'; params.append(review_status)
            if award_level: sql += ' AND sch.award_level=?'; params.append(award_level)
            if grade_id: sql += ' AND st.grade_id=?'; params.append(grade_id)
            if class_type_ids:
                ids = [int(x) for x in class_type_ids.split(',') if x.strip()]
                if ids:
                    sql += f" AND st.class_type_id IN ({','.join(['?']*len(ids))})"
                    params.extend(ids)

            total = conn.execute(f'SELECT COUNT(*) FROM ({sql})', params).fetchone()[0]
            sql += ' ORDER BY CASE sch.award_level WHEN "一等奖" THEN 1 WHEN "二等奖" THEN 2 WHEN "三等奖" THEN 3 ELSE 4 END, sch.language_avg DESC LIMIT ? OFFSET ?'
            params.extend([page_size, (page - 1) * page_size])
            rows = conn.execute(sql, params).fetchall()
            return {'total': total, 'page': page, 'page_size': page_size, 'items': [dict(r) for r in rows]}

    # --- Phase 3+ 新增 ---
    def create_screen_run(self, name, grade_id, category, class_id, exam_ids, created_at, conn=None):
        cur = self._execute_sql(conn,
            """INSERT INTO scholarship_screen_runs (name, grade_id, category, class_id, exam_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, grade_id, category, class_id, exam_ids, created_at))
        return cur.lastrowid

    def delete_by_run(self, screen_run_id, conn=None):
        self._execute_sql(conn, 'DELETE FROM scholarships WHERE screen_run_id = ?', (screen_run_id,))

    def upsert_candidate(self, student_id, exam_id, class_id, average_score, language_avg, professional_avg,
                         total_score=None, subjects_json=None, category=None, screen_run_id=None,
                         grade_rank=None, major_rank=None, award_level=None, review_status='待复核',
                         conn=None):
        cur = self._execute_sql(conn,
            """INSERT OR REPLACE INTO scholarships
               (student_id, exam_id, class_id, average_score, language_avg, professional_avg,
                total_score, subjects, category, screen_run_id, grade_rank, major_rank,
                award_level, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (student_id, exam_id, class_id, average_score, language_avg, professional_avg,
             total_score, subjects_json, category, screen_run_id, grade_rank, major_rank,
             award_level, review_status))
        return cur.lastrowid

    # --- 原始 Phase 3 前已有方法 (被截断丢失, 重建) ---
    # 以下方法从 routers/scholarship.py 和 services/scholarship_engine.py 的调用重建

    def review(self, candidate_id, review_status, review_note='', reviewed_by='管理员'):
        """审核候选人."""
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE scholarships SET review_status=?, review_note=?, reviewed_by=?, reviewed_at=datetime("now") WHERE id=?',
                (review_status, review_note, reviewed_by, candidate_id))
            conn.commit()

    def batch_confirm(self, ids):
        """批量确认候选人."""
        if not ids: return 0
        ph = ','.join(['?'] * len(ids))
        with self.get_connection() as conn:
            conn.execute(f'UPDATE scholarships SET review_status="已确认" WHERE id IN ({ph})', tuple(ids))
            conn.commit()
            return len(ids)

    def special_first_prize(self, candidate_id):
        """特殊一等奖（职普融通班等）."""
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE scholarships SET award_level="一等奖", review_status="已确认" WHERE id=?',
                (candidate_id,))
            conn.commit()

    def manual_first_prize(self, student_id, exam_id, class_id, average_score, language_avg, professional_avg,
                           total_score, subjects, category, **kwargs):
        """人工指定一等奖 — 返回新 record id."""
        import json as _json
        with self.get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO scholarships
                   (student_id, exam_id, class_id, average_score, language_avg, professional_avg,
                    total_score, subjects, category, award_level, review_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '一等奖', '已确认')""",
                (student_id, exam_id, class_id, average_score, language_avg, professional_avg,
                 total_score, _json.dumps(subjects, ensure_ascii=False), category))
            conn.commit()
            return cur.lastrowid

    def get_averages(self, student_id, exam_id):
        """获取某学生某考试的语文/专业课平均分 (用于 manual_first_prize)."""
        from database import get_db as _get_db
        with _get_db() as conn:
            row = conn.execute(
                'SELECT chinese_converted as lang, professional_converted as prof FROM scores WHERE student_id=? AND exam_id=?',
                (student_id, exam_id)).fetchone()
            if row:
                return row['lang'] or 0, row['prof'] or 0
            return 0, 0

    def stats(self):
        """奖学金统计."""
        with self.get_connection() as conn:
            total = conn.execute('SELECT COUNT(*) FROM scholarships').fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='待复核'").fetchone()[0]
            confirmed = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='已确认'").fetchone()[0]
            rejected = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='不合格'").fetchone()[0]
            return {'total': total, 'pending': pending, 'confirmed': confirmed, 'rejected': rejected}


    # --- 别名: scholarship_engine.py 用 ScholarshipRepository ---
ScholarshipRepository = ScholarshipCandidateRepository
