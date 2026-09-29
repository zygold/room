import json, os, re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from config import UPLOAD_DIR
from repositories.classes import ClassRepository
from repositories.teachers import TeacherRepository
from repositories.timetables import TimetableImportRepository, TimetableMappingRepository
from services import timetable_parser
from services.stats_engine import unaligned_subjects
from services.excel_parser import normalize_class_name
from utils.common import now_str
from utils.logger import log_operation

router = APIRouter()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class_repo = ClassRepository()
teacher_repo = TeacherRepository()
import_repo = TimetableImportRepository()
mapping_repo = TimetableMappingRepository()


class ConfirmTimetable(BaseModel):
    replace: Optional[bool] = False


def _safe_filename(filename: str) -> str:
    name = os.path.basename((filename or "").replace("", "/"))
    name = re.sub(r"[^\w\.\-\u4e00-\u9fa5]", "_", name or "")
    return name


def _find_existing_class(class_name: str):
    normalized = normalize_class_name(class_name)
    if not normalized:
        return None
    return class_repo.find_by_name_with_variants(normalized)


def _resolve_mappings(content_class, content_teacher):
    names = timetable_parser.teacher_names(content_teacher)
    detailed = timetable_parser.parse_class_timetable_detailed(content_class, teacher_names=names)
    if not detailed:
        cv = timetable_parser.parse_class_timetable(content_class)
        tv = timetable_parser.parse_teacher_timetable(content_teacher)
        conflicts = timetable_parser.cross_validate(cv, tv)
        return {"conflicts": conflicts, "mappings": [], "unmatched": [], "unmapped_subjects": []}

    mappings, unmatched = [], set()
    for cls_title, subject, teacher_raw, slot in detailed:
        class_info = _find_existing_class(cls_title)
        teacher = timetable_parser.resolve_teacher_prefix(teacher_raw, names)
        if teacher is None or class_info is None:
            if class_info is None:
                unmatched.add(cls_title)
            continue
        mappings.append({
            "class_id": class_info["id"],
            "class_name": cls_title,
            "subject_name": subject,
            "teacher_name": teacher,
            "slot": slot,
        })
    subject_names = sorted({m["subject_name"] for m in mappings if m.get("subject_name")})
    unmapped = []
    if subject_names:
        with mapping_repo.get_connection() as conn:
            unmapped = unaligned_subjects(conn, subject_names)
    return {"conflicts": [], "mappings": mappings,
            "unmatched": sorted(unmatched), "unmapped_subjects": unmapped}


def _mark_combined(mappings, school_year, semester):
    groups = {}
    for m in mappings:
        key = (m["subject_name"], m["teacher_name"], school_year, semester)
        groups.setdefault(key, []).append(m)
    for group in groups.values():
        distinct_classes = {m["class_id"] for m in group}
        is_combined = len(distinct_classes) >= 2
        all_names = sorted({m["class_name"] for m in group})
        for m in group:
            m["is_combined"] = 1 if is_combined else 0
            if is_combined:
                m["combined_class_names"] = json.dumps([n for n in all_names if n != m["class_name"]], ensure_ascii=False)
            else:
                m["combined_class_names"] = None
    return mappings


def _dedupe_mappings(mappings):
    seen = {}
    for m in mappings:
        key = (m["class_id"], m["subject_name"], m["teacher_name"])
        if key not in seen:
            seen[key] = m
    return list(seen.values())


@router.post("/upload")
async def upload_timetable(
    class_file: UploadFile = File(...),
    teacher_file: UploadFile = File(...),
    school_year: str = Form(...),
    semester: str = Form(...),
):
    class_content = await class_file.read()
    teacher_content = await teacher_file.read()
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_class = _safe_filename(class_file.filename)
    safe_teacher = _safe_filename(teacher_file.filename)
    class_path = UPLOAD_DIR / f"ttb_class_{ts}_{safe_class}"
    teacher_path = UPLOAD_DIR / f"ttb_teacher_{ts}_{safe_teacher}"
    with open(class_path, "wb") as f:
        f.write(class_content)
    with open(teacher_path, "wb") as f:
        f.write(teacher_content)

    import_id = import_repo.create(
        class_file.filename, teacher_file.filename,
        str(class_path), str(teacher_path), school_year, semester,
    )
    log_operation("课表上传", f"上传班级课表 {class_file.filename} 与教师课表 {teacher_file.filename}, 学年 {school_year} 学期 {semester}")
    return {"id": import_id, "class_file_name": class_file.filename, "teacher_file_name": teacher_file.filename, "status": "待确认"}


@router.post("/preview/{import_id}")
def preview_timetable(import_id: int):
    row = import_repo.get_by_id(import_id)
    if not row:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    try:
        class_content = Path(row["class_file_path"]).read_bytes()
        teacher_content = Path(row["teacher_file_path"]).read_bytes()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"读取上传文件失败: {e}")
    result = _resolve_mappings(class_content, teacher_content)
    return {"import_id": import_id, "school_year": row["school_year"], "semester": row["semester"],
            "mappings": result["mappings"], "unmatched": result["unmatched"], "conflicts": result["conflicts"],
            "unmapped_subjects": result["unmapped_subjects"],
            "total": len(result["mappings"])}


@router.post("/confirm/{import_id}")
def confirm_timetable(import_id: int, payload: Optional[ConfirmTimetable] = None):
    payload = payload or ConfirmTimetable()
    row = import_repo.get_by_id(import_id)
    if not row:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    try:
        class_content = Path(row["class_file_path"]).read_bytes()
        teacher_content = Path(row["teacher_file_path"]).read_bytes()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"读取上传文件失败: {e}")

    school_year, semester = row["school_year"], row["semester"]

    if payload.replace:
        mapping_repo.delete_by_year_semester(school_year, semester)

    result = _resolve_mappings(class_content, teacher_content)
    mappings = _dedupe_mappings(result["mappings"])
    mappings = _mark_combined(mappings, school_year, semester)

    saved = 0
    for m in mappings:
        teacher_id = teacher_repo.find_or_create(m["teacher_name"])
        saved += mapping_repo.upsert_mapping(
            m["class_id"], m["class_name"], m["subject_name"],
            teacher_id, m["teacher_name"],
            m["is_combined"], m["combined_class_names"],
            school_year, semester, m["slot"],
        )

    import_repo.update_status(import_id, "已入库", saved, result["unmatched"])

    ht_updated = 0
    try:
        ht_map = timetable_parser.extract_head_teachers(
            class_content, teacher_names=timetable_parser.teacher_names(teacher_content),
        )
        has_ht_col = class_repo.has_head_teacher_column()
        for cls_name, ht_name in ht_map.items():
            cls_row = class_repo.find_id_by_name(cls_name)
            if cls_row:
                if has_ht_col:
                    class_repo.update_head_teacher(cls_row, ht_name)
                class_repo.update_students_homeroom(cls_row, ht_name)
                ht_updated += 1
    except Exception:
        pass

    log_operation("课表确认入库", f"导入批次 {import_id} 学年 {school_year} 学期 {semester}, 保存 {saved} 条映射, 未匹配 {len(result['unmatched'])} 个班级, 自动设置班主任 {ht_updated} 个, 未映射科目 {len(result['unmapped_subjects'])} 个")
    return {"import_id": import_id, "saved": saved, "unmatched": result["unmatched"],
            "unmapped_subjects": result["unmapped_subjects"], "head_teachers_set": ht_updated}


@router.get("/mappings")
def list_mappings(
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    class_id: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
):
    return mapping_repo.list_with_filters(school_year, semester, class_id, teacher_id)


@router.get("/overview")
def overview(school_year: Optional[str] = Query(None), semester: Optional[str] = Query(None)):
    rows = mapping_repo.list_for_overview(school_year, semester)
    groups = {}
    for r in rows:
        key = (r["teacher_name"], r["subject_name"])
        entry = groups.setdefault(key, {
            "teacher_name": r["teacher_name"], "subject_name": r["subject_name"],
            "classes": [], "is_combined": False,
        })
        entry["classes"].append(r["class_name"])
        if r["is_combined"]:
            entry["is_combined"] = True
    result = []
    for entry in groups.values():
        entry["class_count"] = len(entry["classes"])
        result.append(entry)
    return result


@router.delete("/mappings")
def delete_mappings(school_year: str, semester: str):
    deleted = mapping_repo.delete_by_year_semester(school_year, semester)
    import_repo.mark_cleared_by_year_semester(school_year, semester)
    log_operation("课表清除", f"删除学年 {school_year} 学期 {semester} 的 {deleted} 条课表映射")
    return {"deleted": deleted}
