"""Operation log audit APIs."""
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import get_db
from utils.common import now_str
from utils.logger import log_operation

router = APIRouter()


@router.get("/")
def list_logs(
    operation_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    operator: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
):
    """Query operation logs with filters and pagination."""
    with get_db() as conn:
        sql = "SELECT * FROM operation_logs WHERE 1=1"
        params = []
        if operation_type:
            sql += " AND operation_type=?"
            params.append(operation_type)
        if status:
            sql += " AND status=?"
            params.append(status)
        if operator:
            sql += " AND operator LIKE ?"
            params.append(f"%{operator}%")
        if keyword:
            sql += " AND (operation_type LIKE ? OR operation_detail LIKE ?)"
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        if start_date:
            sql += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND created_at < ?"
            params.append(end_date)

        total = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        rows = conn.execute(sql, params).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


@router.get("/types")
def list_log_types():
    """Return distinct operation types for filtering."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT operation_type FROM operation_logs ORDER BY operation_type"
        ).fetchall()
    return [r["operation_type"] for r in rows]


@router.get("/export")
def export_logs(
    operation_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    operator: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    fmt: str = Query("xlsx"),
):
    """Export filtered operation logs."""
    with get_db() as conn:
        sql = "SELECT * FROM operation_logs WHERE 1=1"
        params = []
        if operation_type:
            sql += " AND operation_type=?"
            params.append(operation_type)
        if status:
            sql += " AND status=?"
            params.append(status)
        if operator:
            sql += " AND operator LIKE ?"
            params.append(f"%{operator}%")
        if keyword:
            sql += " AND (operation_type LIKE ? OR operation_detail LIKE ?)"
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        if start_date:
            sql += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND created_at < ?"
            params.append(end_date)
        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, params).fetchall()

    filename = f"operation_logs_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if fmt.lower() == "csv":
        import csv
        bio = io.StringIO()
        writer = csv.writer(bio)
        writer.writerow(["ID", "操作类型", "详情", "操作人", "状态", "时间"])
        for r in rows:
            writer.writerow([r["id"], r["operation_type"], r["operation_detail"], r["operator"], r["status"], r["created_at"]])
        bio.seek(0)
        return StreamingResponse(
            iter([bio.getvalue().encode("utf-8-sig")]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )
    else:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "操作日志"
        ws.append(["ID", "操作类型", "详情", "操作人", "状态", "时间"])
        for r in rows:
            ws.append([r["id"], r["operation_type"], r["operation_detail"], r["operator"], r["status"], r["created_at"]])
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        return StreamingResponse(
            iter([bio.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
        )


class CleanupPayload(BaseModel):
    days: int


@router.post("/cleanup")
def cleanup_logs(payload: CleanupPayload):
    """Delete logs older than the specified number of days."""
    if payload.days < 1:
        raise HTTPException(status_code=400, detail="保留天数必须大于 0")
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM operation_logs WHERE created_at < datetime('now', ?)",
            (f"-{payload.days} days",),
        )
        deleted = cur.rowcount
        conn.commit()
    log_operation("日志清理", f"删除 {deleted} 条 {payload.days} 天前的操作日志")
    return {"deleted": deleted}
