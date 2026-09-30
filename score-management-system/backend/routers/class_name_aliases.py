"""班级别名对照表维护路由（来源文件写法 -> 班级档案正式名）。"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db
from repositories.class_name_aliases import ClassNameAliasesRepository
from utils.logger import log_operation

router = APIRouter()
alias_repo = ClassNameAliasesRepository()


def _normalize_alias(raw: str) -> str:
    """与 excel_parser.normalize_class_name 的查表键保持一致：去空白 + 全角括号转半角。"""
    return (raw or "").strip().replace("（", "(").replace("）", ")")


class ClassNameAliasCreate(BaseModel):
    alias: str
    canonical_name: str


def _class_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM classes WHERE name=?", (name,)).fetchone() is not None


@router.get("/class-name-aliases")
def list_class_name_aliases():
    """列出全部班级别名映射。"""
    items = alias_repo.list_all()
    return {"items": items, "total": len(items)}


@router.get("/class-name-aliases/options")
def list_alias_options():
    """可选的正式班级（供下拉框使用）。"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT c.name, g.name AS grade_name, m.name AS major_name
               FROM classes c
               JOIN grades g ON c.grade_id = g.id
               JOIN majors m ON c.major_id = m.id
               ORDER BY g.id, c.name"""
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/class-name-aliases")
def create_class_name_alias(req: ClassNameAliasCreate):
    """新增或更新一条别名映射。"""
    alias = _normalize_alias(req.alias)
    canonical = (req.canonical_name or "").strip()
    if not alias or not canonical:
        raise HTTPException(400, "别名与正式班级名称均不能为空")
    if alias == canonical:
        raise HTTPException(400, "别名与正式班级名称相同，无需登记")
    with get_db() as conn:
        if not _class_exists(conn, canonical):
            raise HTTPException(
                400, "正式班级「%s」不在班级档案中，请先在「班级管理」里新增" % canonical)
        existing = alias_repo.find_canonical(alias, conn=conn)
        if existing == canonical:
            raise HTTPException(400, "该别名已指向「%s」" % canonical)
        alias_repo.upsert(canonical, alias, conn=conn)
    log_operation("班级别名维护", "%s -> %s" % (alias, canonical))
    return {"ok": True, "alias": alias, "canonical_name": canonical,
            "replaced": existing or None}


@router.delete("/class-name-aliases/{alias_id}")
def delete_class_name_alias(alias_id: int):
    """删除一条别名映射。"""
    row = alias_repo.get_by_id(alias_id)
    if not row:
        raise HTTPException(404, "别名不存在")
    deleted = alias_repo.delete(alias_id)
    log_operation("班级别名维护", "删除别名 %s -> %s" % (row["alias"], row["canonical_name"]))
    return {"ok": True, "deleted": deleted}
