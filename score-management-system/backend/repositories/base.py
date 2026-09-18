"""Repository 层基类 — 所有具体 Repository 继承它."""
from database import get_db


class BaseRepository:
    """SQLite 单表 CRUD 的薄封装 + 批量操作."""

    table: str | None = None
    pk: str = "id"

    def get_connection(self):
        """给子类一个统一的连接入口 — 与 router 层用同一个 get_db context manager."""
        return get_db()

    def _resolve_conn(self, conn=None):
        """返回 (conn, own_conn). 外部传入则复用（不 close），否则自己开."""
        if conn is not None:
            return conn, False
        return self.get_connection(), True

    def _execute_sql(self, sql, params=(), conn=None, commit=True):
        """通用执行：支持复用外部 conn. commit 仅在 own_conn=True 时生效."""
        conn, own = self._resolve_conn(conn)
        try:
            cur = conn.execute(sql, params)
            if commit and own:
                conn.commit()
            return cur
        finally:
            if own:
                conn.close()

    # ---- 单表通用 CRUD（模板方法）----

    def get_by_id(self, record_id: int):
        with self.get_connection() as conn:
            return conn.execute(
                f"SELECT * FROM {self.table} WHERE {self.pk}=?", (record_id,)
            ).fetchone()

    def get_all(self):
        with self.get_connection() as conn:
            return conn.execute(f"SELECT * FROM {self.table}").fetchall()

    def delete_by_id(self, record_id: int) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                f"DELETE FROM {self.table} WHERE {self.pk}=?", (record_id,)
            )
            conn.commit()
            return cur.rowcount

    def count(self, where: str = "", params: tuple = (), conn=None) -> int:
        sql = f"SELECT COUNT(*) FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        cur, own = self._resolve_conn(conn)
        try:
            return cur.execute(sql, params).fetchone()[0]
        finally:
            if own: cur.connection.close()

    def count_table(self, table_name: str, where: str = "", params: tuple = (), conn=None) -> int:
        """Count rows in arbitrary table (backup_manager 用)."""
        sql = f"SELECT COUNT(*) FROM {table_name}"
        if where:
            sql += f" WHERE {where}"
        cur, own = self._resolve_conn(conn)
        try:
            return cur.execute(sql, params).fetchone()[0]
        finally:
            if own: cur.connection.close()

    def execute(self, sql: str, params: tuple = ()):
        """原始 SQL 通道 — 子类复杂查询用. 调用方自己 commit."""
        with self.get_connection() as conn:
            return conn.execute(sql, params)

    def executemany(self, sql: str, params_seq: list, conn=None):
        cur, own = self._resolve_conn(conn)
        try:
            cur.executemany(sql, params_seq)
            cur.connection.commit()
        finally:
            if own: cur.connection.close()

    # --- 通用查询封装 (Service 层动态 SQL 用) ---

    def query(self, sql: str, params=None, conn=None, as_dict=True):
        """Execute arbitrary SQL SELECT, return list of dicts."""
        cur, own = self._resolve_conn(conn)
        try:
            params = params or ()
            rows = cur.execute(sql, params).fetchall()
            return [dict(r) for r in rows] if as_dict else rows
        finally:
            if own: cur.connection.close()

    def query_one(self, sql: str, params=None, conn=None):
        """Execute arbitrary SQL, return single dict or None."""
        cur, own = self._resolve_conn(conn)
        try:
            params = params or ()
            row = cur.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            if own: cur.connection.close()

    def execute_dml(self, sql: str, params=None, conn=None, commit=True):
        """Execute INSERT/UPDATE/DELETE, return cursor."""
        cur, own = self._resolve_conn(conn)
        try:
            params = params or ()
            cur.execute(sql, params)
            if commit and cur.connection:
                cur.connection.commit()
            return cur
        finally:
            if own: cur.connection.close()
