from .base import BaseRepository


class ScoreSubjectDetailRepository(BaseRepository):
    table = 'score_subject_details'
    pk = 'id'

    # --- 原始方法 ---
    def delete_by_score(self, score_id, conn=None):
        self._execute_sql(
            'DELETE FROM score_subject_details WHERE score_id=?',
            (score_id,), conn=conn, commit=False)

    def insert_detail(self, score_id, subject_name, original_score, max_score, conn=None):
        self._execute_sql(
            'INSERT INTO score_subject_details (score_id, subject_name, original_score, max_score) VALUES (?, ?, ?, ?)',
            (score_id, subject_name, original_score, max_score),
            conn=conn, commit=False)

    # --- Phase 3+ 新增 ---
    def get_by_score(self, score_id, conn=None):
        return self._execute_sql(conn,
            'SELECT id, original_score, max_score FROM score_subject_details WHERE score_id=?',
            (score_id,))

    def get_by_scores(self, score_ids, conn=None):
        if not score_ids:
            return []
        ph = ','.join(['?'] * len(score_ids))
        return self._execute_sql(conn,
            f'SELECT score_id, subject_name, original_score, converted_score FROM score_subject_details WHERE score_id IN ({ph})',
            tuple(score_ids))

    def update_converted(self, detail_id, converted_score, conn=None):
        self._execute_sql(conn,
            'UPDATE score_subject_details SET converted_score=? WHERE id=?',
            (converted_score, detail_id))

    def list_subjects_by_score(self, score_id, conn=None):
        rows = self._execute_sql(conn,
            'SELECT DISTINCT subject_name FROM score_subject_details WHERE score_id=?',
            (score_id,))
        return [r["subject_name"] for r in rows]
