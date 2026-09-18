"""OperationLogRepository — 操作日志表的数据访问层."""
from .base import BaseRepository
from typing import Optional


class OperationLogRepository(BaseRepository):
    table = "operation_logs"
    pk = "id"

    # ---------- 列表查询（带动态 WHERE + 分页）----------

    def build_where_clause(
        self,
        operation_type: Optional[str] = None,
        status: Optional[str] = None,
        operator: Optional[str] = None,
        keyword: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """返回 (where_clause, params_list) — 供 list_logs / export_logs 复用."""
        conditions = []
        params = []
        if operation_type:
            conditions.append("operation_type = ?")
            params.append(operation_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if operator:
            conditions.append("operator LIKE ?")
            params.append(f"%{operator}%")
        if keyword:
            conditions.append("(operation_type LIKE ? OR operation_detail LIKE ?)")
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        if start_date:
            conditions.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("created_at < ?")
            params.append(end_date)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else "WHERE 1=1"
        return where, params

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        operation_type: Optional[str] = None,
        status: Optional[str] = None,
        operator: Optional[str] = None,
        keyword: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """分页查询 + 过滤."""
        where, params = self.build_where_clause(
            operation_type, status, operator, keyword, start_date, end_date
        )
        with self.get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM operation_logs {where}", params
            ).fetchone()[0]
            sql = f"SELECT * FROM operation_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?"
            rows = conn.execute(
                sql, params + [page_size, (page - 1) * page_size]
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [dict(r) for r in rows],
        }

    def list_types(self) -> list:
        """去重的操作类型列表."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT operation_type FROM operation_logs ORDER BY operation_type"
            ).fetchall()
        return [r["operation_type"] for r in rows]

    def for_export(
        self,
        operation_type: Optional[str] = None,
        status: Optional[str] = None,
        operator: Optional[str] = None,
        keyword: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list:
        """导出用 — 不分页, 全部拿回来."""
        where, params = self.build_where_clause(
            operation_type, status, operator, keyword, start_date, end_date
        )
        with self.get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM operation_logs {where} ORDER BY id DESC", params
            ).fetchall()
        return [dict(r) for r in rows]

    def cleanup_older_than_days(self, days: int) -> int:
        """删除 N 天前的旧日志. 返回删除行数."""
        with self.get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM operation_logs WHERE created_at < datetime('now', ?)",
                (f"-{days} days",),
            )
            conn.commit()
            return cur.rowcount

    def insert_log(
        self, operation_type: str, operation_detail: str, operator: str,
        status: str = "成功"
    ):
        """写一条日志 — 给 log_operation 内部调用."""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO operation_logs (operation_type, operation_detail, operator, status, created_at)"
                " VALUES (?, ?, ?, ?, datetime('now'))",
                (operation_type, operation_detail, operator, status),
            )
            conn.commit()
