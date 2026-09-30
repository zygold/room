"""专业科目别名维护路由 (方案2: 课表科目名 -> 成绩科目名)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_db
from repositories.subject_aliases import SubjectAliasRepository
from services.stats_engine import refresh_subject_aliases, unaligned_subjects
from utils.logger import log_operation

router = APIRouter()
alias_repo = SubjectAliasRepository()


class SubjectAliasCreate(BaseModel):
    alias: str
    standard_subject: str
    subject_type: Optional[str] = None


@router.get("/subject-aliases")
def list_subject_aliases():
    """列出全部专业科目别名映射。"""
    items = alias_repo.list_all()
    return {"items": items, "total": len(items)}


@router.get("/subject-aliases/unmapped")
def list_unmapped_subjects(school_year: str = Query(...), semester: str = Query(...)):
    """某学期课表中, 未能与成绩侧科目对齐的专业科目名 (仅提示, 不写库)。"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT subject_name FROM timetable_mappings "
            "WHERE school_year=? AND semester=? ORDER BY subject_name",
            (school_year, semester)).fetchall()
        names = [r["subject_name"] for r in rows]
        unmapped = unaligned_subjects(conn, names)
    return {"school_year": school_year, "semester": semester,
            "subjects": names, "unmapped": unmapped, "unmapped_count": len(unmapped)}


@router.post("/subject-aliases")
def create_subject_alias(req: SubjectAliasCreate):
    """新增或更新一条别名映射。"""
    alias = (req.alias or "").strip()
    standard = (req.standard_subject or "").strip()
    if not alias or not standard:
        raise HTTPException(400, "别名与标准科目名均不能为空")
    alias_repo.upsert(alias, standard, req.subject_type)
    refresh_subject_aliases()
    log_operation("科目别名维护", f"新增/更新 {alias} -> {standard}")
    return {"ok": True, "alias": alias, "standard_subject": standard,
            "subject_type": req.subject_type}


@router.delete("/subject-aliases/{alias_id}")
def delete_subject_alias(alias_id: int):
    """删除一条别名映射。"""
    deleted = alias_repo.delete(alias_id)
    if not deleted:
        raise HTTPException(404, "别名不存在")
    refresh_subject_aliases()
    log_operation("科目别名维护", f"删除别名 id={alias_id}")
    return {"ok": True, "deleted": deleted}
