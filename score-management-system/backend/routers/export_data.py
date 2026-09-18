"""Data export APIs — Repository 重构版."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from repositories.exports import ExportRecordRepository
from services.export_generator import fetch_data, generate
from utils.common import now_str, sizeof_fmt
from utils.logger import log_operation

router = APIRouter()
export_repo = ExportRecordRepository()


class ExportPayload(BaseModel):
    export_type: str
    filter_condition: dict
    format: str
    options: dict = {}


@router.post("/preview")
def preview_export(payload: ExportPayload):
    rows = fetch_data(payload.filter_condition)
    return {"total": len(rows), "items": rows[:10]}


@router.post("/generate")
def generate_export(payload: ExportPayload):
    fmt = payload.format.lower()
    desensitize = payload.options.get("desensitize", False)
    path, size = generate(payload.filter_condition, fmt, desensitize, payload.options)
    record_id = export_repo.create(
        export_type=payload.export_type,
        filter_condition_json=json.dumps(payload.filter_condition, ensure_ascii=False),
        fmt=fmt,
        file_path=str(path),
        file_size=sizeof_fmt(size),
        options_json=json.dumps(payload.options, ensure_ascii=False),
        created_at=now_str(),
    )
    log_operation("导出名单", f"生成 {fmt} 文件 {path.name}")
    return {"id": record_id, "file_path": str(path), "file_name": path.name, "file_size": sizeof_fmt(size)}


@router.get("/download/{record_id}")
def download_export(record_id: int):
    row = export_repo.get_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail="导出记录不存在")
    path = Path(row["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已删除")
    return FileResponse(path, filename=path.name)


@router.get("/history")
def export_history():
    return export_repo.get_all()


@router.delete("/delete/{record_id}")
def delete_export(record_id: int):
    row = export_repo.get_by_id(record_id)
    if row:
        path = Path(row["file_path"])
        if path.exists():
            path.unlink()
    export_repo.delete_by_id(record_id)
    return {"deleted": record_id}
