"""Backup and restore APIs."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import get_db
from services.backup_manager import (
    create_backup,
    restore_backup,
    preview_restore,
    get_db_size,
    get_data_snapshot,
    BACKUP_DIR,
)
from utils.common import now_str, sizeof_fmt
from utils.logger import log_operation

router = APIRouter()


class BackupCreate(BaseModel):
    backup_type: str = "手动备份"
    description: str = ""
    encrypt: bool = False
    password: str = ""


DEFAULT_BACKUP_CONFIG = {
    "on_close": True,
    "after_import": True,
    "scheduled": False,
    "scheduled_time": "22:00",
    "retention_days": 30,
    "destinations": ["local"],
    "encrypt": False,
}


@router.get("/config")
def get_backup_config():
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'backup_%'").fetchall()
    config = dict(DEFAULT_BACKUP_CONFIG)
    for r in rows:
        key = r["key"].replace("backup_", "", 1)
        value = r["value"]
        if key in ("on_close", "after_import", "scheduled", "encrypt"):
            value = value.lower() in ("true", "1", "yes")
        elif key == "retention_days":
            try:
                value = int(value)
            except ValueError:
                value = 30
        elif key == "destinations":
            value = [v.strip() for v in value.split(",") if v.strip()]
        config[key] = value
    return config


@router.put("/config")
def update_backup_config(payload: dict):
    with get_db() as conn:
        for key, value in payload.items():
            db_key = f"backup_{key}"
            if isinstance(value, bool):
                value = "true" if value else "false"
            elif isinstance(value, list):
                value = ",".join(str(v) for v in value)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
                (db_key, str(value), str(value)),
            )
        conn.commit()
    log_operation("备份配置", f"更新 {list(payload.keys())}")
    return {"updated": list(payload.keys())}


@router.get("/restore-preview/{backup_id}")
def restore_preview(backup_id: int):
    try:
        snapshot = preview_restore(backup_id)
        with get_db() as conn:
            current = {
                "students": conn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
                "exams": conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0],
                "scores": conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0],
                "classes": conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0],
                "majors": conn.execute("SELECT COUNT(*) FROM majors").fetchone()[0],
            }
        return {"backup": snapshot, "current": current}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/list")
def list_backups():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM backups ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@router.get("/storage")
def storage_info():
    total = 0
    if BACKUP_DIR.exists():
        for f in BACKUP_DIR.iterdir():
            if f.is_file():
                total += f.stat().st_size
    size_str = get_db_size()
    return {
        "db_size": size_str,
        "backup_total_size": sizeof_fmt(total),
        "backup_total_bytes": total,
        "data_snapshot": get_data_snapshot(),
    }


@router.post("/create")
def create_backup_endpoint(payload: BackupCreate):
    try:
        backup_id, path = create_backup(
            backup_type=payload.backup_type,
            description=payload.description,
            encrypt=payload.encrypt,
            password=payload.password or None,
        )
        log_operation("创建备份", f"备份ID {backup_id}, 类型 {payload.backup_type}")
        return {"id": backup_id, "file_path": str(path)}
    except Exception as e:
        log_operation("创建备份", f"失败: {e}", status="失败")
        raise HTTPException(status_code=500, detail=f"备份失败: {e}")


class RestorePayload(BaseModel):
    password: str = ""


@router.post("/restore/{backup_id}")
def restore_backup_endpoint(backup_id: int, payload: RestorePayload = None):
    try:
        pwd = payload.password if payload else None
        restore_backup(backup_id, password=pwd or None)
        log_operation("恢复备份", f"备份ID {backup_id}")
        return {"restored": backup_id}
    except Exception as e:
        log_operation("恢复备份", f"失败: {e}", status="失败")
        raise HTTPException(status_code=500, detail=f"恢复失败: {e}")


@router.get("/download/{backup_id}")
def download_backup(backup_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="备份不存在")
    path = Path(row["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="备份文件已丢失")
    return FileResponse(path, filename=path.name)


@router.delete("/delete/{backup_id}")
def delete_backup(backup_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
        if row:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
            conn.execute("DELETE FROM backups WHERE id=?", (backup_id,))
            conn.commit()
    log_operation("删除备份", f"备份ID {backup_id}")
    return {"deleted": backup_id}
