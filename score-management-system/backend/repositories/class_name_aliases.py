from .base import BaseRepository


class ClassNameAliasesRepository(BaseRepository):
    """class_name_aliases table access."""

    def find_canonical(self, alias, conn=None):
        rows = self.query('SELECT canonical_name FROM class_name_aliases WHERE alias=?', (alias,), conn=conn)
        return rows[0]["canonical_name"] if rows else None
