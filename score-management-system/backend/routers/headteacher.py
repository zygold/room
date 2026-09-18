"""班主任批量导入路由 (Repository 重构版)."""
import uuid
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from repositories.headteachers import HeadteacherRepository
from repositories.classes import ClassRepository
from repositories.classes import ClassRepository
from services.headteacher_importer import (
    parse_headteacher_file,
    resolve_and_prepare,
)
from database import get_db

router = APIRouter()

_PREVIEW_CACHE = {}
_CACHE_TTL_SECONDS = 3600

ht_repo = HeadteacherRepository()
class_repo = ClassRepository()
class_repo = ClassRepository()


class ConfirmHeadteacherRequest(BaseModel):
    session_id: str
    override: Optional[bool] = True


@router.post("/headteacher/preview")
async def preview_headteacher(file: UploadFile = File(...)):
    if not file.filename or not (file.filename.lower().endswith(".xlsx") or file.filename.lower().endswith(".xls")):
        raise HTTPException(400, "只支持 .xlsx / .xls 格式")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件过大 (>10MB)")

    pairs = parse_headteacher_file(content)
    if not pairs:
        return {"session_id": None, "total_parsed": 0, "matched": [], "unmatched_class": [],
                "message": "未能解析到任何班级-班主任对"}

    with get_db() as conn:
        result = resolve_and_prepare(conn, pairs)

    sid = str(uuid.uuid4())
    _PREVIEW_CACHE[sid] = result

    return {
        "session_id": sid,
        "total_parsed": len(pairs),
        "matched": [
            {"class_id": m[0], "class_name": m[1], "head_teacher": m[2], "class_raw": m[3]}
            for m in result["matched"]
        ],
        "unmatched_class": [
            {"class_raw": u[0], "head_raw": u[1]} for u in result["unmatched_class"]
        ],
        "summary": {
            "matched_count": len(result["matched"]),
            "unmatched_count": len(result["unmatched_class"]),
        },
    }


@router.post("/headteacher/confirm")
def confirm_headteacher(req: ConfirmHeadteacherRequest):
    result = _PREVIEW_CACHE.pop(req.session_id, None)
    if result is None:
        raise HTTPException(404, "预览会话已过期或不存在, 请重新上传")

    matched = result["matched"]
    if not matched:
        return {"applied": 0, "unmatched_class": result["unmatched_class"], "message": "没有可应用的匹配"}

    if not req.override:
        existing = ht_repo.get_ids_with_head_teacher()
        matched = [m for m in matched if m[0] not in existing]

    applied = ht_repo.apply_batch(matched)

    return {
        "applied": applied,
        "unmatched_class": [
            {"class_raw": u[0], "head_raw": u[1]} for u in result["unmatched_class"]
        ],
        "message": f"成功更新 {applied} 个班级的班主任",
    }


@router.get("/headteacher/overview")
def overview_headteacher():
    return class_repo.overview()

