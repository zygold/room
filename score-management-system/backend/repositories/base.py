"""Repository 层基类 — 所有具体 Repository 继承它."""
from contextlib import contextmanager

from database import get_db


class BaseRepository:
    """SQLite 单表 CRUD 的薄封装 + 批量操作."""

    table: str | None = None
    pk: str = "id"

    def get_connection(self):
        """给子类一个统一的连接入口 — 与 router 层用同一个 get_db context manager."""
        return get_db()

    @contextmanager
    def _resolve_conn(self, conn=None):
        """连接解析: 外部传入则复用(不关闭), 否则自动开新连接并在退出时关闭."""
        if conn is not None:
            yield conn
        else:
            with self.get_connection() as conn:
                yield conn

    def _execute_sql(self, sql, params=(), conn=None, commit=True):
        """通用执行：支持复用外部 conn. commit 仅在自有连接时生效."""
        own = conn is None
        with self._resolve_conn(conn) as conn:
            cur = conn.execute(sql, params)
            if commit and own:
                conn.commit()
            return cur

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
        with self._resolve_conn(conn) as conn:
            return conn.execute(sql, params).fetchone()[0]

    def count_table(self, table_name: str, where: str = "", params: tuple = (), conn=None) -> int:
        """Count rows in arbitrary table (backup_manager 用)."""
        sql = f"SELECT COUNT(*) FROM {table_name}"
        if where:
            sql += f" WHERE {where}"
        with self._resolve_conn(conn) as conn:
            return conn.execute(sql, params).fetchone()[0]

    def execute(self, sql: str, params: tuple = ()):
        """原始 SQL 通道 — 子类复杂查询用. 调用方自己 commit."""
        with self.get_connection() as conn:
            return conn.execute(sql, params)

    def executemany(self, sql: str, params_seq: list, conn=None):
        with self._resolve_conn(conn) as conn:
            conn.executemany(sql, params_seq)
            conn.commit()

    # --- 通用查询封装 (Service 层动态 SQL 用) ---

    def query(self, sql: str, params=None, conn=None, as_dict=True):
        """Execute arbitrary SQL SELECT, return list of dicts."""
        params = params or ()
        with self._resolve_conn(conn) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows] if as_dict else rows

    def query_one(self, sql: str, params=None, conn=None):
        """Execute arbitrary SQL, return single dict or None."""
        params = params or ()
        with self._resolve_conn(conn) as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def execute_dml(self, sql: str, params=None, conn=None, commit=True):
        """Execute INSERT/UPDATE/DELETE, return cursor."""
        params = params or ()
        with self._resolve_conn(conn) as conn:
            cur = conn.execute(sql, params)
            if commit:
                conn.commit()
            return cur
