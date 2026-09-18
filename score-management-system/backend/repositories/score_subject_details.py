from .base import BaseRepository


class ScoreSubjectDetailRepository(BaseRepository):
    table = 'score_subject_details'
    pk = 'id'

    # --- 原始方法 ---
    def delete_by_score(self, score_id, conn=None):
        with self._resolve_conn(conn) as conn:
            conn.execute('DELETE FROM score_subject_details WHERE score_id=?', (score_id,))

    def insert_detail(self, score_id, subject_name, original_score, max_score, conn=None):
        with self._resolve_conn(conn) as conn:
            conn.execute(
                'INSERT INTO score_subject_details (score_id, subject_name, original_score, max_score) VALUES (?, ?, ?, ?)',
                (score_id, subject_name, original_score, max_score))

    # --- Phase 3+ 新增 ---
    def get_by_score(self, score_id, conn=None):
        return self.query(
            'SELECT id, original_score, max_score FROM score_subject_details WHERE score_id=?',
            (score_id,), conn=conn)

    def get_by_scores(self, score_ids, conn=None):
        if not score_ids:
            return []
        ph = ','.join(['?'] * len(score_ids))
        return self.query(
            f'SELECT score_id, subject_name, original_score, converted_score FROM score_subject_details WHERE score_id IN ({ph})',
            tuple(score_ids), conn=conn)

    def update_converted(self, detail_id, converted_score, conn=None):
        self.execute_dml(
            'UPDATE score_subject_details SET converted_score=? WHERE id=?',
            (converted_score, detail_id), conn=conn, commit=False)

    def list_subjects_by_score(self, score_id, conn=None):
        rows = self.query(
            'SELECT DISTINCT subject_name FROM score_subject_details WHERE score_id=?',
            (score_id,), conn=conn)
        return [r["subject_name"] for r in rows]
