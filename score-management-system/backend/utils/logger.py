"""Operation log helpers."""
from datetime import datetime
from sqlite3 import Connection
from database import get_db


def log_operation(operation_type: str, detail: str = "", operator: str = "管理员", status: str = "成功", conn: Connection = None):
    """记录操作日志。若传入 conn，则在同一事务中写入；否则开启独立连接。"""
    now = datetime.now().isoformat(timespec='seconds')
    params = (operation_type, detail, operator, status, now)
    sql = "INSERT INTO operation_logs (operation_type, operation_detail, operator, status, created_at) VALUES (?, ?, ?, ?, ?)"
    if conn is not None:
        conn.execute(sql, params)
        return
    with get_db() as conn:
        conn.execute(sql, params)
        conn.commit()
