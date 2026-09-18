from .base import BaseRepository


class DashboardRepository(BaseRepository):
    table = None  # 多表聚合, 不用通用 CRUD

    def overview_counts(self) -> dict:
        with self.get_connection() as conn:
            students = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]
            exams = conn.execute('SELECT COUNT(*) FROM exams').fetchone()[0]
            scores = conn.execute('SELECT COUNT(*) FROM scores').fetchone()[0]
            pending_scores = conn.execute("SELECT COUNT(*) FROM scores WHERE is_converted=0").fetchone()[0]
            scholarships = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='待复核'").fetchone()[0]
            backups = conn.execute('SELECT COUNT(*) FROM backups').fetchone()[0]
            imports = conn.execute('SELECT COUNT(*) FROM import_files').fetchone()[0]
            return {'students': students, 'exams': exams, 'scores': scores,
                    'pending_scores': pending_scores, 'pending_scholarships': scholarships,
                    'backups': backups, 'imports': imports}

    def grade_stats(self) -> list:
        with self.get_connection() as conn:
            rows = conn.execute(
                '''SELECT g.name, COUNT(s.id) as student_count
                   FROM grades g LEFT JOIN students s ON s.grade_id = g.id
                   GROUP BY g.id ORDER BY g.id'''
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_exams(self, limit=5) -> list:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                'SELECT id, name, exam_type, exam_date FROM exams ORDER BY id DESC LIMIT ?', (limit,)
            ).fetchall()]

    def recent_logs(self, limit=5) -> list:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                'SELECT operation_type, operation_detail, status, created_at FROM operation_logs ORDER BY id DESC LIMIT ?',
                (limit,)
            ).fetchall()]

    def tasks_data(self) -> dict:
        with self.get_connection() as conn:
            pending_conversion = conn.execute("SELECT COUNT(*) FROM scores WHERE is_converted=0").fetchone()[0]
            pending_reviews = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='待复核'").fetchone()[0]
            pending_validation = conn.execute("SELECT COUNT(*) FROM import_files WHERE validation_status='待校验'").fetchone()[0]
            latest_backup = conn.execute('SELECT MAX(created_at) FROM backups').fetchone()[0]
            return {'pending_conversion': pending_conversion, 'pending_reviews': pending_reviews,
                    'pending_validation': pending_validation, 'latest_backup': latest_backup}

    def recent_operations(self, limit=10) -> list:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                'SELECT operation_type, operation_detail, status, created_at FROM operation_logs ORDER BY id DESC LIMIT ?',
                (limit,)
            ).fetchall()]

    def snapshot_counts(self) -> dict:
        """backup restore-preview 用."""
        with self.get_connection() as conn:
            return {
                'students': conn.execute('SELECT COUNT(*) FROM students').fetchone()[0],
                'exams': conn.execute('SELECT COUNT(*) FROM exams').fetchone()[0],
                'scores': conn.execute('SELECT COUNT(*) FROM scores').fetchone()[0],
                'classes': conn.execute('SELECT COUNT(*) FROM classes').fetchone()[0],
                'majors': conn.execute('SELECT COUNT(*) FROM majors').fetchone()[0],
            }
