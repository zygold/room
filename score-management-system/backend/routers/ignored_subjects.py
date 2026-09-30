"""未映射科目忽略名单维护路由."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_db
from repositories.ignored_subjects import IgnoredSubjectRepository
from services.stats_engine import refresh_ignored_subjects, _is_ignored_subject
from utils.logger import log_operation

router = APIRouter()
ignored_repo = IgnoredSubjectRepository()


class IgnoredSubjectCreate(BaseModel):
    pattern: str
    note: Optional[str] = None


@router.get("/ignored-subjects")
def list_ignored_subjects():
    """列出忽略名单条目。"""
    items = ignored_repo.list_all()
    return {"items": items, "total": len(items)}


@router.get("/ignored-subjects/subjects")
def list_subject_options(school_year: Optional[str] = None, semester: Optional[str] = None):
    """列出课表科目名及是否已忽略 (供勾选页使用)。"""
    sql = "SELECT DISTINCT subject_name FROM timetable_mappings"
    params = []
    if school_year and semester:
        sql += " WHERE school_year=? AND semester=?"
        params = [school_year, semester]
    sql += " ORDER BY subject_name"
    with get_db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        ignored_map = {r["pattern"]: r["id"] for r in conn.execute(
            "SELECT id, pattern FROM ignored_subjects")}
        items = [{"subject_name": r["subject_name"],
                  "ignored": _is_ignored_subject(r["subject_name"], conn=conn),
                  "id": ignored_map.get((r["subject_name"] or "").strip())}
                 for r in rows]
    return {"items": items, "total": len(items),
            "ignored_count": sum(1 for i in items if i["ignored"])}


@router.post("/ignored-subjects")
def add_ignored_subject(req: IgnoredSubjectCreate):
    """新增忽略项 (科目名)。"""
    pattern = (req.pattern or "").strip()
    if not pattern:
        raise HTTPException(400, "科目名不能为空")
    ignored_repo.add(pattern, req.note)
    refresh_ignored_subjects()
    log_operation("忽略名单维护", f"新增忽略科目 {pattern}")
    return {"ok": True, "pattern": pattern, "note": req.note}


@router.delete("/ignored-subjects/{item_id}")
def delete_ignored_subject(item_id: int):
    """移除忽略项。"""
    deleted = ignored_repo.delete(item_id)
    if not deleted:
        raise HTTPException(404, "忽略项不存在")
    refresh_ignored_subjects()
    log_operation("忽略名单维护", f"移除忽略科目 id={item_id}")
    return {"ok": True, "deleted": deleted}
