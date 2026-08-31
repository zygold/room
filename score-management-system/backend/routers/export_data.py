"""Data export APIs."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import get_db
from services.export_generator import fetch_data, generate, EXPORT_DIR
from utils.common import now_str, sizeof_fmt
from utils.logger import log_operation

router = APIRouter()


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
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO export_records (export_type, filter_condition, format, file_path, file_size, options, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (payload.export_type, json.dumps(payload.filter_condition, ensure_ascii=False), fmt,
             str(path), sizeof_fmt(size), json.dumps(payload.options, ensure_ascii=False), now_str()),
        )
        conn.commit()
    log_operation("导出名单", f"生成 {fmt} 文件 {path.name}")
    return {"id": cur.lastrowid, "file_path": str(path), "file_name": path.name, "file_size": sizeof_fmt(size)}


@router.get("/download/{record_id}")
def download_export(record_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM export_records WHERE id=?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="导出记录不存在")
    path = Path(row["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已删除")
    return FileResponse(path, filename=path.name)


@router.get("/history")
def export_history():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM export_records ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@router.delete("/delete/{record_id}")
def delete_export(record_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM export_records WHERE id=?", (record_id,)).fetchone()
        if row:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
        conn.execute("DELETE FROM export_records WHERE id=?", (record_id,))
        conn.commit()
    return {"deleted": record_id}
