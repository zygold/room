from .base import BaseRepository
from utils.common import now_str
import json


class ImportFileRepository(BaseRepository):
    table = 'import_files'
    pk = 'id'

    def create(self, file_name, grade_id, major_id, exam_type, school_year, semester, month, subject_config) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                '''INSERT INTO import_files (file_name, grade_id, major_id, exam_type, school_year, semester, month,
                   student_count, validation_status, subject_config, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (file_name, grade_id, major_id, exam_type, school_year, semester, month,
                 0, '待校验', subject_config, now_str()),
            )
            conn.commit()
            return cur.lastrowid

    def update_after_save(self, file_id: int, file_path: str, student_count: int):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE import_files SET file_path=?, student_count=? WHERE id=?',
                (file_path, student_count, file_id),
            )
            conn.commit()

    def update_validation_status(self, file_id: int, status: str, duplicate_count=0, missing_count=0):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE import_files SET validation_status=?, duplicate_count=?, missing_count=? WHERE id=?',
                (status, duplicate_count, missing_count, file_id),
            )
            conn.commit()

    def mark_imported(self, file_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE import_files SET validation_status='已导入' WHERE id=?", (file_id,))
            conn.commit()

    def list_all(self) -> list:
        return self.get_all()

    def get_by_ids(self, ids: list) -> list:
        with self.get_connection() as conn:
            placeholders = ','.join(['?'] * len(ids))
            return [dict(r) for r in conn.execute(
                f'SELECT * FROM import_files WHERE id IN ({placeholders})', ids
            ).fetchall()]

    def delete_with_file(self, file_id: int) -> str | None:
        """返回 file_path (调用方负责删文件) 或 None."""
        with self.get_connection() as conn:
            row = conn.execute('SELECT file_path FROM import_files WHERE id=?', (file_id,)).fetchone()
            path = row['file_path'] if row else None
            conn.execute('DELETE FROM import_files WHERE id=?', (file_id,))
            conn.commit()
            return path


    def update_file_info(self, file_id, file_path, student_count):
        with self.get_connection() as conn:
            conn.execute('UPDATE import_files SET file_path=?, student_count=? WHERE id=?',
                (file_path, student_count, file_id))
            conn.commit()

    def update_validation(self, file_id, status, duplicate_count, missing_count):
        with self.get_connection() as conn:
            conn.execute('UPDATE import_files SET validation_status=?, duplicate_count=?, missing_count=? WHERE id=?',
                (status, duplicate_count, missing_count, file_id))
            conn.commit()

    def delete_record(self, file_id):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM import_files WHERE id=?', (file_id,))
            conn.commit()

class FileSubjectMappingRepository(BaseRepository):
    table = 'file_subject_mappings'
    pk = 'id'

    def replace_all_for_file(self, import_file_id: int, subject_config: dict):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM file_subject_mappings WHERE import_file_id=?', (import_file_id,))
            type_map = {'语文': 'chinese', '数学': 'math', '英语': 'english', '物理': 'physics',
                        '化学': 'chemistry', '生物': 'biology', '政治': 'politics',
                        '历史': 'history', '地理': 'geography', '专业课': 'professional', '总分': 'total'}
            for idx, (name, cfg) in enumerate(subject_config.items()):
                if not name or not isinstance(name, str):
                    continue
                max_score = cfg.get('max_score') if isinstance(cfg, dict) else cfg
                try: max_score = float(max_score)
                except (ValueError, TypeError): max_score = None
                conn.execute(
                    '''INSERT INTO file_subject_mappings
                       (import_file_id, column_index, column_header, subject_type, subject_name, max_score)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (import_file_id, idx, name, type_map.get(name, 'unknown'), name, max_score),
                )
            conn.commit()
