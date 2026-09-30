"""ignored_subjects table access — 未映射科目忽略名单 (精确科目名)."""
from datetime import datetime

from .base import BaseRepository


class IgnoredSubjectRepository(BaseRepository):
    """忽略名单访问."""

    table = 'ignored_subjects'
    pk = 'id'

    def list_all(self, conn=None):
        return self.query(
            "SELECT id, pattern, note, created_at FROM ignored_subjects "
            "ORDER BY note, pattern", conn=conn)

    def load_set(self, conn=None):
        """返回 {科目名} 集合."""
        rows = self.query("SELECT pattern FROM ignored_subjects", conn=conn)
        return {r["pattern"] for r in rows if r["pattern"]}

    def add(self, pattern, note=None, conn=None):
        pattern = (pattern or "").strip()
        if not pattern:
            return False
        self.execute_dml(
            "INSERT INTO ignored_subjects (pattern, note, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(pattern) DO UPDATE SET note=excluded.note",
            (pattern, note, datetime.now().isoformat(timespec='seconds')), conn=conn)
        return True

    def delete(self, item_id):
        return self.delete_by_id(item_id)
