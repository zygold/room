from .base import BaseRepository


class ClassNameAliasesRepository(BaseRepository):
    """class_name_aliases table access."""

    table = "class_name_aliases"
    pk = "id"

    def find_canonical(self, alias, conn=None):
        rows = self.query('SELECT canonical_name FROM class_name_aliases WHERE alias=?', (alias,), conn=conn)
        return rows[0]["canonical_name"] if rows else None

    def list_all(self, conn=None):
        return self.query(
            'SELECT id, canonical_name, alias FROM class_name_aliases ORDER BY id', conn=conn)

    def upsert(self, canonical_name, alias, conn=None):
        """按 alias 唯一键写入/更新映射。"""
        if self.find_canonical(alias, conn=conn):
            self.execute_dml(
                'UPDATE class_name_aliases SET canonical_name=? WHERE alias=?',
                (canonical_name, alias), conn=conn)
        else:
            self.execute_dml(
                'INSERT INTO class_name_aliases (canonical_name, alias) VALUES (?, ?)',
                (canonical_name, alias), conn=conn)
        return True

    def delete(self, alias_id, conn=None):
        cur = self.execute_dml('DELETE FROM class_name_aliases WHERE id=?', (alias_id,), conn=conn)
        return cur.rowcount > 0
