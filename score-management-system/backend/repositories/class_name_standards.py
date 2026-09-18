from .base import BaseRepository


class ClassNameStandardsRepository(BaseRepository):
    """class_name_standards table access."""

    def find_by_name(self, name, conn=None):
        rows = self._execute_sql(conn, 'SELECT name FROM class_name_standards WHERE name=?', (name,))
        return rows[0]["name"] if rows else None
