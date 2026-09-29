"""subject_aliases table access — 专业科目别名映射 (课表科目名 → 成绩科目名)."""
from datetime import datetime

from .base import BaseRepository


class SubjectAliasRepository(BaseRepository):
    """专业科目别名映射表访问."""

    table = 'subject_aliases'
    pk = 'id'

    def list_all(self, conn=None):
        return self.query(
            "SELECT id, alias, standard_subject, subject_type, created_at "
            "FROM subject_aliases ORDER BY standard_subject, alias",
            conn=conn)

    def load_map(self, conn=None):
        """返回 {alias: standard_subject} 映射."""
        rows = self.query(
            "SELECT alias, standard_subject FROM subject_aliases", conn=conn)
        return {r["alias"]: r["standard_subject"] for r in rows if r["alias"]}

    def find_standard(self, alias, conn=None):
        """按别名查标准科目名, 未命中返回 None."""
        if not alias:
            return None
        row = self.query_one(
            "SELECT standard_subject FROM subject_aliases WHERE alias=?",
            (str(alias).strip(),), conn=conn)
        return row["standard_subject"] if row else None

    def upsert(self, alias, standard_subject, subject_type=None, conn=None):
        """新增或更新一条别名映射."""
        alias = (alias or "").strip()
        standard_subject = (standard_subject or "").strip()
        if not alias or not standard_subject:
            return False
        self.execute_dml(
            "INSERT INTO subject_aliases (alias, standard_subject, subject_type, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(alias) DO UPDATE SET "
            "standard_subject=excluded.standard_subject, subject_type=excluded.subject_type",
            (alias, standard_subject, subject_type,
             datetime.now().isoformat(timespec='seconds')),
            conn=conn)
        return True

    def delete(self, alias_id):
        return self.delete_by_id(alias_id)
