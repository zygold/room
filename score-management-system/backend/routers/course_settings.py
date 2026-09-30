"""课程设置导入路由 — 文件解析、与课表来源对比、确认入库."""
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from config import UPLOAD_DIR
from repositories.classes import ClassRepository
from repositories.course_settings import (
    CourseSettingImportRepository,
    CourseSettingRepository,
    COURSE_FILE_EXTS,
)
from repositories.timetables import TimetableMappingRepository
from services.course_file_parser import parse_course_file
from services.excel_parser import normalize_class_name
from services.timetable_parser import _normalize_subject_name
from utils.logger import log_operation

router = APIRouter()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class_repo = ClassRepository()
import_repo = CourseSettingImportRepository()
setting_repo = CourseSettingRepository()
mapping_repo = TimetableMappingRepository()


class ConfirmCourseSettings(BaseModel):
    replace: Optional[bool] = False


def _safe_filename(filename):
    name = os.path.basename((filename or "").replace("\\", "/"))
    name = re.sub(r"[^\w\.\-\u4e00-\u9fa5]", "_", name or "")
    return name or "course_settings"


_BRACKET_NOISE = re.compile(r"[【\[][^】\]]{0,8}[】\]]")


def _candidate_names(raw):
    """生成班级名候选，顺序为「最忠实原值 → 逐步放宽」。

    Excel 里的班级名常带 【实习】/（本方）/ 全角括号 等噪声，
    直接跑 normalize_class_name 反而会把能精确命中的名字改坏，
    因此先试原值，再逐步剥离噪声、最后才用归一化结果。
    """
    s = str(raw or "").strip()
    if not s:
        return []
    out = []

    def add(value):
        value = (value or "").strip()
        if value and value not in out:
            out.append(value)

    add(s)
    add(s.replace("（", "(").replace("）", ")"))            # 全角括号 → 半角
    stripped = _BRACKET_NOISE.sub("", s).strip()            # 去掉 【实习】 这类标记
    add(stripped)
    add(stripped.replace("（", "(").replace("）", ")"))
    if stripped.endswith("职普"):                           # 25级电子6班(本方)职普
        add(stripped[:-2])
    for base in (s, stripped):
        if not base:
            continue
        try:
            add(normalize_class_name(base))
        except Exception:
            pass
    return out


def _lookup_class(conn, name):
    row = conn.execute(
        "SELECT id, name, grade_id FROM classes WHERE name=?", (name,)
    ).fetchone()
    return dict(row) if row else None


def _match_class(raw_class):
    """返回 (classes 行 dict 或 None, 命中的候选名或 None)。"""
    with class_repo.get_connection() as conn:
        for cand in _candidate_names(raw_class):
            hit = _lookup_class(conn, cand)
            if hit:
                return hit, cand
    return None, None


def _resolve_rows(rows):
    """为每行匹配班级，返回 (带匹配信息的行, 未匹配班级名列表)。"""
    resolved, unmatched = [], []
    for r in rows:
        raw_class = r["class_name"]
        hit, matched_cand = _match_class(raw_class)
        item = dict(r)
        item["normalized_course_name"] = _normalize_subject_name(r["course_name"])
        if hit:
            item["class_id"] = hit["id"]
            item["grade_id"] = hit.get("grade_id")
            # 统一用班级档案里的正式名，才能与课表来源对齐
            item["normalized_class_name"] = hit["name"]
            item["match_note"] = None if matched_cand == raw_class.strip() else "名称已归一"
        else:
            item["class_id"] = None
            item["grade_id"] = None
            item["normalized_class_name"] = raw_class
            item["match_note"] = None
            if raw_class not in unmatched:
                unmatched.append(raw_class)
        resolved.append(item)
    return resolved, unmatched


def _timetable_pairs(school_year, semester):
    """课表来源的 (班级名, 归一科目名) 集合。"""
    sql = ("SELECT c.name AS class_name, m.subject_name FROM timetable_mappings m "
           "JOIN classes c ON c.id = m.class_id WHERE 1=1")
    params = []
    if school_year:
        sql += " AND m.school_year=?"
        params.append(school_year)
    if semester:
        sql += " AND m.semester=?"
        params.append(semester)
    with mapping_repo.get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return {(r["class_name"], _normalize_subject_name(r["subject_name"])) for r in rows}


def _pair_diff(file_pairs, tt_pairs):
    both = file_pairs & tt_pairs
    only_file = file_pairs - tt_pairs
    only_tt = tt_pairs - file_pairs
    file_subjects = {s for _, s in file_pairs}
    tt_subjects = {s for _, s in tt_pairs}
    return {
        "file_total": len(file_pairs),
        "timetable_total": len(tt_pairs),
        "both_count": len(both),
        "only_file": [{"class_name": c, "course_name": s} for c, s in sorted(only_file)],
        "only_timetable": [{"class_name": c, "course_name": s} for c, s in sorted(only_tt)],
        "subject_only_file": sorted(file_subjects - tt_subjects),
        "subject_only_timetable": sorted(tt_subjects - file_subjects),
        "subject_both": sorted(file_subjects & tt_subjects),
    }


@router.post("/course-settings/upload")
async def upload_course_settings(
    file: UploadFile = File(...),
    school_year: str = Form(""),
    semester: str = Form(""),
):
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件内容为空")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in COURSE_FILE_EXTS:
        raise HTTPException(400, "不支持的文件格式，仅支持 Excel / Word / PDF")
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    path = UPLOAD_DIR / ("course_settings_%s_%s" % (ts, _safe_filename(file.filename)))
    with open(path, "wb") as f:
        f.write(content)
    import_id = import_repo.create(file.filename, str(path), school_year, semester)
    log_operation("课程设置上传", "上传课程设置文件 %s" % file.filename)
    return {"import_id": import_id, "file_name": file.filename, "status": "待确认"}


@router.post("/course-settings/preview/{import_id}")
def preview_course_settings(import_id: int):
    row = import_repo.get_by_id(import_id)
    if not row:
        raise HTTPException(404, "导入批次不存在")
    try:
        with open(row["file_path"], "rb") as f:
            rows = parse_course_file(row["file_name"], f.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, "解析失败: %s" % e)

    resolved, unmatched = _resolve_rows(rows)
    tt_pairs = _timetable_pairs(row["school_year"], row["semester"])
    file_pairs = {(r["normalized_class_name"], r["normalized_course_name"])
                  for r in resolved if r["class_id"]}
    comparison = _pair_diff(file_pairs, tt_pairs)
    for r in resolved:
        r["in_timetable"] = bool(r["class_id"]) and (
            (r["normalized_class_name"], r["normalized_course_name"]) in tt_pairs)

    return {
        "import_id": import_id,
        "file_name": row["file_name"],
        "school_year": row["school_year"],
        "semester": row["semester"],
        "total": len(resolved),
        "matched_count": sum(1 for r in resolved if r["class_id"]),
        "unmatched_classes": unmatched,
        "items": resolved,
        "comparison": comparison,
    }


@router.post("/course-settings/confirm/{import_id}")
def confirm_course_settings(import_id: int, payload: Optional[ConfirmCourseSettings] = None):
    payload = payload or ConfirmCourseSettings()
    row = import_repo.get_by_id(import_id)
    if not row:
        raise HTTPException(404, "导入批次不存在")
    try:
        with open(row["file_path"], "rb") as f:
            rows = parse_course_file(row["file_name"], f.read())
    except Exception as e:
        raise HTTPException(400, "解析失败: %s" % e)

    resolved, unmatched = _resolve_rows(rows)
    if payload.replace:
        setting_repo.delete_by_source_file(row["file_name"])

    saved = 0
    for r in resolved:
        setting_repo.upsert(
            course_name=r["course_name"],
            class_id=r["class_id"],
            class_name=r["normalized_class_name"],
            teacher_name=r["teacher_name"] or None,
            periods=r["periods"],
            grade_id=r["grade_id"],
            source="文件导入",
            source_file=row["file_name"],
            school_year=row["school_year"],
            semester=row["semester"],
            status="已确认",
            note=("原班级名: %s" % r["class_name"]) if r["class_name"] != r["normalized_class_name"] else None,
        )
        saved += 1

    import_repo.update_status(import_id, "已入库", saved, unmatched)
    log_operation("课程设置入库",
                  "批次 %d 文件 %s, 入库 %d 条, 未匹配班级 %d 个"
                  % (import_id, row["file_name"], saved, len(unmatched)))
    return {"import_id": import_id, "saved": saved, "unmatched_classes": unmatched}


@router.get("/course-settings")
def list_course_settings(
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    items = setting_repo.list_all(school_year, semester, source, status)
    return {"items": items, "total": len(items)}


@router.get("/course-settings/compare")
def compare_course_settings(
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
):
    """已入库的课程设置 vs 课表来源，用于核对课程口径。"""
    stored = setting_repo.list_all(school_year, semester, source)
    file_pairs = {(r["class_name"], _normalize_subject_name(r["course_name"]))
                  for r in stored if r.get("class_name")}
    tt_pairs = _timetable_pairs(school_year, semester)
    result = _pair_diff(file_pairs, tt_pairs)
    result["stored_total"] = len(stored)
    result["source_files"] = sorted({r["source_file"] for r in stored if r.get("source_file")})
    return result
