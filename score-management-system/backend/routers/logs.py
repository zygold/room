"""Operation log audit APIs — Repository 重构版."""
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from repositories.operation_logs import OperationLogRepository
from utils.logger import log_operation

router = APIRouter()
log_repo = OperationLogRepository()


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
    return log_repo.list(
        page=page, page_size=page_size,
        operation_type=operation_type, status=status,
        operator=operator, keyword=keyword,
        start_date=start_date, end_date=end_date,
    )


@router.get("/types")
def list_log_types():
    """Return distinct operation types for filtering."""
    return log_repo.list_types()


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
    rows = log_repo.for_export(
        operation_type=operation_type, status=status,
        operator=operator, keyword=keyword,
        start_date=start_date, end_date=end_date,
    )
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
    deleted = log_repo.cleanup_older_than_days(payload.days)
    log_operation("日志清理", f"删除 {deleted} 条 {payload.days} 天前的操作日志")
    return {"deleted": deleted}
