"""ExportRecordRepository — 导出记录表的数据访问层."""
from .base import BaseRepository


class ExportRecordRepository(BaseRepository):
    table = "export_records"
    pk = "id"

    def create(
        self, export_type: str, filter_condition_json: str, fmt: str,
        file_path: str, file_size: str, options_json: str, created_at: str
    ) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO export_records "
                "(export_type, filter_condition, format, file_path, file_size, options, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (export_type, filter_condition_json, fmt, file_path, file_size, options_json, created_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_all(self) -> list:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM export_records ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
