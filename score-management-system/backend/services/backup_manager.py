"""Backup and restore manager."""
import os
import shutil
import sqlite3
import zipfile
from pathlib import Path
from datetime import datetime

from config import BACKUP_DIR, DB_PATH
from database import get_db

BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def get_db_size() -> str:
    size = os.path.getsize(DB_PATH) if DB_PATH.exists() else 0
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}TB"


def get_data_snapshot() -> str:
    with get_db() as conn:
        students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        exams = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
        scores = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        mappings = conn.execute("SELECT COUNT(*) FROM timetable_mappings").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return f"学生{students}/考试{exams}/成绩{scores}/课表映射{mappings}/用户{users}"


def create_backup(backup_type: str = "手动备份", description: str = "", encrypt: bool = False, password: str = None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"score_backup_{timestamp}"
    db_copy = BACKUP_DIR / f"{base_name}.db"
    # 使用 SQLite 在线备份 API，避免复制正在写入的数据库导致不一致
    with get_db() as conn:
        bconn = sqlite3.connect(str(db_copy))
        try:
            with bconn:
                conn.backup(bconn)
        finally:
            bconn.close()

    if encrypt and password:
        zip_path = BACKUP_DIR / f"{base_name}.zip"
        arcname = f"{base_name}.db"
        try:
            import pyzipper
            with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES256) as zf:
                zf.setpassword(password.encode("utf-8"))
                zf.write(db_copy, arcname=arcname)
            is_encrypted = 1
        except Exception:
            # 降级为普通压缩（不加密）
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(db_copy, arcname=arcname)
            is_encrypted = 0
        db_copy.unlink()
        final_path = zip_path
    else:
        final_path = db_copy
        is_encrypted = 0

    size = get_db_size()
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO backups (backup_type, file_path, file_size, description, data_snapshot, is_encrypted, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (backup_type, str(final_path), size, description, get_data_snapshot(), is_encrypted, datetime.now().isoformat(timespec='seconds')),
        )
        conn.commit()
    return cur.lastrowid, final_path


def preview_restore(backup_id: int, password: str = None) -> dict:
    """Return a snapshot of the backup without modifying current DB."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not row:
        raise ValueError("备份不存在")
    path = Path(row["file_path"])
    if not path.exists():
        raise ValueError("备份文件已丢失")

    target_db = path
    temp_dir = None
    if path.suffix == ".zip":
        temp_dir = BACKUP_DIR / "temp_preview"
        temp_dir.mkdir(exist_ok=True)
        pwd = password.encode("utf-8") if password else None
        try:
            import pyzipper
            with pyzipper.AESZipFile(path, "r") as zf:
                if pwd:
                    zf.setpassword(pwd)
                zf.extractall(temp_dir)
        except Exception:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(temp_dir, pwd=pwd)
        db_files = list(temp_dir.glob("*.db"))
        if not db_files:
            raise ValueError("备份压缩包中未找到数据库文件")
        target_db = db_files[0]

    import sqlite3
    bconn = sqlite3.connect(target_db)
    bconn.row_factory = sqlite3.Row
    try:
        snapshot = {
            "students": bconn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
            "exams": bconn.execute("SELECT COUNT(*) FROM exams").fetchone()[0],
            "scores": bconn.execute("SELECT COUNT(*) FROM scores").fetchone()[0],
            "classes": bconn.execute("SELECT COUNT(*) FROM classes").fetchone()[0],
            "majors": bconn.execute("SELECT COUNT(*) FROM majors").fetchone()[0],
            "timetable_mappings": bconn.execute("SELECT COUNT(*) FROM timetable_mappings").fetchone()[0],
            "users": bconn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        }
    finally:
        bconn.close()
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return snapshot


def restore_backup(backup_id: int, password: str = None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not row:
        raise ValueError("备份不存在")
    path = Path(row["file_path"])
    if not path.exists():
        raise ValueError("备份文件已丢失")

    # If encrypted zip, extract first
    target_db = path
    if path.suffix == ".zip":
        temp_dir = BACKUP_DIR / "temp_restore"
        temp_dir.mkdir(exist_ok=True)
        pwd = password.encode("utf-8") if password else None
        try:
            import pyzipper
            with pyzipper.AESZipFile(path, "r") as zf:
                if pwd:
                    zf.setpassword(pwd)
                zf.extractall(temp_dir)
        except Exception:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(temp_dir, pwd=pwd)
        db_files = list(temp_dir.glob("*.db"))
        if not db_files:
            raise ValueError("备份压缩包中未找到数据库文件")
        target_db = db_files[0]

    # Replace current db
    if DB_PATH.exists():
        DB_PATH.replace(BACKUP_DIR / f"score_management_before_restore_{datetime.now().strftime('%Y%m%d%H%M%S')}.db")
    shutil.copy2(target_db, DB_PATH)

    # Cleanup temp
    if path.suffix == ".zip":
        shutil.rmtree(temp_dir, ignore_errors=True)
    return True
