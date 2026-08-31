"""Score data import APIs."""
import os
import re
import zipfile
import io
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from database import get_db, _infer_class_type_id
from services.excel_parser import parse_score_file, normalize_class_name, _read_with_engines, _clean_value, parse_score_file_with_meta
from utils.logger import log_operation
from config import UPLOAD_DIR
from utils.common import now_str

router = APIRouter()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename: str) -> str:
    """去除路径分隔符与危险字符，防止目录遍历。"""
    name = os.path.basename(filename.replace("\\", "/"))
    name = re.sub(r'[^\w\.\-\u4e00-\u9fa5]', '_', name)
    return name


def _parse_teacher_file(content: bytes, filename: str) -> List[Dict[str, str]]:
    """Parse a teacher-class mapping file. Expected columns: 班主任, 班级."""
    try:
        df = _read_with_engines(io.BytesIO(content), sheet_name=0, header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法读取文件：{e}")

    header_row = None
    for idx, row in df.iterrows():
        row_text = " ".join(str(x) for x in row if pd.notna(x))
        if "班主任" in row_text and "班级" in row_text:
            header_row = idx
            break

    if header_row is None:
        raise HTTPException(status_code=400, detail="无法识别班主任明细表头，需包含‘班主任’和‘班级’列")

    df = pd.read_excel(io.BytesIO(content), header=header_row)

    teacher_col = None
    class_col = None
    for col in df.columns:
        col_str = str(col)
        if "班主任" in col_str and teacher_col is None:
            teacher_col = col
        if "班级" in col_str and class_col is None:
            class_col = col

    if teacher_col is None or class_col is None:
        raise HTTPException(status_code=400, detail="无法定位‘班主任’或‘班级’列")

    results = []
    for _, row in df.iterrows():
        teacher = _clean_value(row[teacher_col])
        class_name = _clean_value(row[class_col])
        if teacher is not None and class_name is not None:
            results.append({
                "teacher_name": str(teacher).strip(),
                "class_name": str(class_name).strip(),
            })
    return results


@router.post("/upload-teachers")
async def upload_teachers(file: UploadFile = File(...)):
    """Upload a teacher-class mapping file and update students.homeroom_teacher."""
    content = await file.read()
    mappings = _parse_teacher_file(content, file.filename)

    safe_name = _safe_filename(file.filename)
    saved_path = UPLOAD_DIR / f"teacher_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    with open(saved_path, "wb") as f:
        f.write(content)

    with get_db() as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM students WHERE homeroom_teacher IS NOT NULL AND homeroom_teacher != ''"
        ).fetchone()[0]

        updated_classes = 0
        for item in mappings:
            class_name = normalize_class_name(item["class_name"], conn=conn)
            teacher = item["teacher_name"]
            if not class_name or not teacher:
                continue
            cur = conn.execute(
                "UPDATE students SET homeroom_teacher=? WHERE class_id IN (SELECT id FROM classes WHERE name=?)",
                (teacher, class_name),
            )
            if cur.rowcount > 0:
                updated_classes += 1

        conn.commit()
        after = conn.execute(
            "SELECT COUNT(*) FROM students WHERE homeroom_teacher IS NOT NULL AND homeroom_teacher != ''"
        ).fetchone()[0]

    log_operation("班主任导入", f"上传 {file.filename}，更新 {updated_classes} 个班级，{after - before} 名学生")
    return {
        "file_name": file.filename,
        "mappings": len(mappings),
        "updated_classes": updated_classes,
        "updated_students": after - before,
    }


def _find_existing_exam(conn, name: str, exam_type: str, school_year: Optional[str], semester: Optional[str], month: Optional[int]) -> Optional[int]:
    """Find an existing exam with the same metadata to avoid duplicates.

    同一考试可以跨年级、跨专业，因此只按 name + exam_type + school_year + semester + month 去重。
    """
    row = conn.execute(
        """SELECT id FROM exams
           WHERE name=? AND exam_type=? AND IFNULL(school_year, '')=IFNULL(?, '')
             AND IFNULL(semester, '')=IFNULL(?, '') AND IFNULL(month, '')=IFNULL(?, '')
           LIMIT 1""",
        (name, exam_type, school_year or '', semester or '', month if month is not None else ''),
    ).fetchone()
    return row["id"] if row else None


def _get_existing_class(conn, class_name: str):
    """严格匹配已有班级；若规范化后仍无法对应到现有班级，返回 None。

    以系统中已设置的班级为准，导入时不再自动创建新班级。
    """
    normalized = normalize_class_name(class_name, conn=conn)
    if not normalized:
        return None

    # 精确匹配规范化后的名称
    row = conn.execute(
        "SELECT id, grade_id, major_id, class_type_id FROM classes WHERE name=?",
        (normalized,),
    ).fetchone()
    if row:
        return dict(row)

    # 兼容（本方）后缀变体
    if normalized.endswith("班（本方）"):
        alt_name = normalized[:-4]  # remove "（本方）"
        row = conn.execute(
            "SELECT id, grade_id, major_id, class_type_id FROM classes WHERE name=?",
            (alt_name,),
        ).fetchone()
        if row:
            return dict(row)

    if "（本方）" not in normalized:
        alt_name = normalized + "（本方）"
        row = conn.execute(
            "SELECT id, grade_id, major_id, class_type_id FROM classes WHERE name=?",
            (alt_name,),
        ).fetchone()
        if row:
            return dict(row)

    return None


def _get_or_create_student(conn, name: str, class_info: dict, grade_id: int, major_id: int, student_no: str = None):
    """Get existing student or create a new one."""
    class_id = class_info["id"]
    
    # 优先按学号匹配
    if student_no:
        row = conn.execute(
            "SELECT id FROM students WHERE student_no=? AND class_id=?",
            (student_no, class_id)
        ).fetchone()
        if row:
            return row["id"]
    
    row = conn.execute("SELECT id FROM students WHERE name=? AND class_id=?", (name, class_id)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO students (name, student_no, grade_id, major_id, class_type_id, class_id, homeroom_teacher, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, student_no, grade_id, major_id, class_info["class_type_id"], class_id, "", now_str()),
    )
    return cur.lastrowid


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    grade_id: Optional[int] = Form(None),
    major_id: Optional[int] = Form(None),
    exam_type: Optional[str] = Form("月考"),
    school_year: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    month: Optional[int] = Form(None),
    subject_config: Optional[str] = Form(None),
):
    """Upload a single score file and create an import record."""
    content = await file.read()

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO import_files (file_name, grade_id, major_id, exam_type, school_year, semester, month, student_count, validation_status, subject_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (file.filename, grade_id, major_id, exam_type, school_year, semester, month, 0, "待校验", subject_config, now_str()),
        )
        conn.commit()
        file_id = cur.lastrowid

    safe_name = _safe_filename(file.filename)
    saved_path = UPLOAD_DIR / f"{file_id}_{safe_name}"
    with open(saved_path, "wb") as f:
        f.write(content)

    # Parse student count
    student_count = 0
    if file.filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                student_count += len(parse_score_file(zf.read(ef), ef))
    else:
        student_count = len(parse_score_file(content, file.filename))

    with get_db() as conn:
        conn.execute(
            "UPDATE import_files SET file_path=?, student_count=? WHERE id=?",
            (str(saved_path), student_count, file_id),
        )
        conn.commit()

    log_operation("数据导入", f"上传文件 {file.filename} ({student_count}条)")
    return {"id": file_id, "file_name": file.filename, "student_count": student_count}


@router.post("/upload-multi")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    grade_id: Optional[int] = Form(None),
    major_id: Optional[int] = Form(None),
    exam_type: Optional[str] = Form("月考"),
    school_year: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    month: Optional[int] = Form(None),
    subject_config: Optional[str] = Form(None),
):
    """Upload multiple score files at once."""
    results = []
    for upload in files:
        content = await upload.read()
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO import_files (file_name, grade_id, major_id, exam_type, school_year, semester, month, student_count, validation_status, subject_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (upload.filename, grade_id, major_id, exam_type, school_year, semester, month, 0, "待校验", subject_config, now_str()),
            )
            conn.commit()
            file_id = cur.lastrowid

        safe_name = _safe_filename(upload.filename)
        saved_path = UPLOAD_DIR / f"{file_id}_{safe_name}"
        with open(saved_path, "wb") as f:
            f.write(content)

        student_count = 0
        if upload.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                    student_count += len(parse_score_file(zf.read(ef), ef))
        else:
            student_count = len(parse_score_file(content, upload.filename))

        with get_db() as conn:
            conn.execute(
                "UPDATE import_files SET file_path=?, student_count=? WHERE id=?",
                (str(saved_path), student_count, file_id),
            )
            conn.commit()

        results.append({"id": file_id, "file_name": upload.filename, "student_count": student_count})
        log_operation("数据导入", f"上传文件 {upload.filename} ({student_count}条)")

    return {"uploaded": results}


@router.get("/files")
def list_import_files():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM import_files ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def _load_records(file_row: sqlite3.Row):
    """Load parsed records from a saved file."""
    saved_path = file_row["file_path"] or _find_saved_file_legacy(file_row)
    if not saved_path or not Path(saved_path).exists():
        raise HTTPException(status_code=404, detail="服务器文件已丢失")

    content = Path(saved_path).read_bytes()
    filename = file_row["file_name"]
    if filename.lower().endswith(".zip"):
        records = []
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                records.extend(parse_score_file(zf.read(ef), ef))
        return records
    return parse_score_file(content, filename)


def _load_records_with_meta(file_row: sqlite3.Row):
    """Load parsed records and detected subject metadata from a saved file."""
    saved_path = file_row["file_path"] or _find_saved_file_legacy(file_row)
    if not saved_path or not Path(saved_path).exists():
        raise HTTPException(status_code=404, detail="服务器文件已丢失")

    content = Path(saved_path).read_bytes()
    filename = file_row["file_name"]
    if filename.lower().endswith(".zip"):
        records = []
        detected_subjects = []
        professional_subjects = []
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                meta = parse_score_file_with_meta(zf.read(ef), ef)
                records.extend(meta["records"])
                detected_subjects.extend(meta.get("detected_subjects", []))
                professional_subjects.extend(meta.get("professional_subjects", []))
        # Deduplicate by name
        detected_map = {item["name"]: item for item in detected_subjects}
        prof_map = {item["name"]: item for item in professional_subjects}
        return {
            "records": records,
            "detected_subjects": list(detected_map.values()),
            "professional_subjects": list(prof_map.values()),
        }
    return parse_score_file_with_meta(content, filename)


def _find_saved_file_legacy(row: sqlite3.Row):
    """Fallback for old records without file_path."""
    prefix = f"{row['created_at'].replace(':', '').replace('-', '').replace(' ', '')}_"
    for p in UPLOAD_DIR.iterdir():
        if p.name.endswith(row["file_name"]) and p.name.startswith(prefix[:14]):
            return str(p)
    return None


@router.post("/validate/{file_id}")
def validate_file(file_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM import_files WHERE id=?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文件不存在")

    meta = _load_records_with_meta(row)
    records = meta["records"]

    errors = []
    warnings = []
    duplicate_count = 0
    missing_count = 0
    unknown_classes = set()

    with get_db() as conn:
        seen = set()
        for rec in records:
            if not rec["name"]:
                errors.append({"row": rec["row_index"], "msg": "姓名缺失", "sheet": rec.get("sheet_name", "")})
                missing_count += 1
                continue

            key = (rec["name"], rec.get("class_name", ""))
            if key in seen:
                warnings.append({"row": rec["row_index"], "msg": f"重复学生 '{rec['name']}'", "sheet": rec.get("sheet_name", "")})
                duplicate_count += 1
            seen.add(key)

            # 严格匹配已有班级
            class_name = rec.get("class_name", "")
            if class_name:
                class_info = _get_existing_class(conn, class_name)
                if not class_info:
                    unknown_classes.add(class_name)

    if unknown_classes:
        sorted_unknown = sorted(unknown_classes)
        errors.append({
            "row": 0,
            "msg": f"以下班级未在系统中设置，请调整或先创建班级：{', '.join(sorted_unknown)}",
            "sheet": "",
            "unknown_classes": sorted_unknown,
        })

    if not records:
        errors.append({"row": 0, "msg": "未解析到任何成绩记录", "sheet": ""})

    status = "校验失败" if errors else "校验通过"
    with get_db() as conn:
        conn.execute(
            "UPDATE import_files SET validation_status=?, duplicate_count=?, missing_count=? WHERE id=?",
            (status, duplicate_count, missing_count, file_id),
        )
        conn.commit()

    # 合并用户上传时携带的 subject_config 默认值（如果有）
    user_config = {}
    if row["subject_config"]:
        try:
            user_config = json.loads(row["subject_config"])
        except Exception:
            pass

    detected_subjects = meta.get("detected_subjects", [])
    professional_subjects = meta.get("professional_subjects", [])

    # 用用户上传时的配置覆盖默认满分
    for item in detected_subjects + professional_subjects:
        name = item["name"]
        if name in user_config:
            try:
                item["max_score"] = float(user_config[name].get("max_score", item["max_score"]))
            except (ValueError, AttributeError):
                pass

    return {
        "status": status,
        "records": len(records),
        "errors": errors[:50],
        "warnings": warnings[:50],
        "duplicate_count": duplicate_count,
        "missing_count": missing_count,
        "unknown_classes": sorted(unknown_classes),
        "detected_subjects": detected_subjects,
        "professional_subjects": professional_subjects,
    }


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def _subject_total(records_dict):
    keys = ["语文", "数学", "英语", "专业课", "物理", "化学", "生物", "政治", "历史", "地理"]
    return sum(_num(records_dict.get(k)) or 0 for k in keys)


def _other_subject_total(records_dict):
    keys = ["物理", "化学", "生物", "政治", "历史", "地理"]
    return sum(_num(records_dict.get(k)) or 0 for k in keys)


def _save_score_subject_details(conn, score_id: int, prof_scores: Dict[str, float], subject_config: Optional[Dict[str, Dict[str, float]]]):
    """Save individual professional subject scores for a score record."""
    if not prof_scores:
        return
    conn.execute("DELETE FROM score_subject_details WHERE score_id=?", (score_id,))
    now = now_str()
    for name, score in prof_scores.items():
        max_score = 100.0
        if subject_config and name in subject_config:
            try:
                max_score = float(subject_config[name].get("max_score", 100))
            except (ValueError, TypeError):
                pass
        conn.execute(
            """INSERT INTO score_subject_details
               (score_id, subject_name, original_score, max_score, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (score_id, name, score, max_score, now),
        )


def _calc_professional_max_score(rec, subject_config: Optional[Dict[str, Dict[str, float]]] = None):
    """Calculate full mark for professional score of a single record."""
    prof_scores = rec.get("professional_subject_scores") or {}
    if prof_scores:
        total = 0.0
        for name, score in prof_scores.items():
            if not name or not isinstance(name, str):
                continue
            norm = name.strip().lower()
            if norm.startswith("unnamed"):
                continue
            max_score = 100.0
            if subject_config and name in subject_config:
                try:
                    max_score = float(subject_config[name].get("max_score", 100))
                except (ValueError, TypeError):
                    pass
            else:
                from services.excel_parser import _extract_max_score_from_header
                extracted = _extract_max_score_from_header(name)
                if extracted is not None:
                    max_score = float(extracted)
            total += max_score
        return total if total > 0 else 100.0

    # No professional subject details: use aggregate professional config if available
    if subject_config and "专业课" in subject_config:
        try:
            return float(subject_config["专业课"].get("max_score", 100))
        except (ValueError, TypeError):
            pass
    return 100.0


class ImportConflictError(Exception):
    """Raised when imported records conflict with existing data."""
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__(f"发现 {len(conflicts)} 条成绩冲突，请人工确认后重试")


class UnknownClassError(Exception):
    """Raised when imported records contain classes not in the system."""
    def __init__(self, unknown_classes):
        self.unknown_classes = unknown_classes
        super().__init__(f"发现 {len(unknown_classes)} 个班级未在系统中设置，请调整班级名称或先创建班级")


def _resolve_student_id(conn, rec, class_info, exam_id=None):
    """匹配学生身份。

    优先级：
    1. 按学号+班级匹配
    2. 按姓名+班级匹配
    3. 如果同班同姓名存在多条记录，优先选择未参加本次考试的记录（用于合并分散成绩）
    """
    class_id = class_info["id"]
    student_no = str(rec.get("student_no") or "").strip()
    name = rec["name"].strip()

    # 1. 学号匹配（最可靠）
    if student_no:
        row = conn.execute(
            "SELECT id FROM students WHERE student_no=? AND class_id=?",
            (student_no, class_id)
        ).fetchone()
        if row:
            return row["id"]

    # 2. 姓名+班级匹配
    rows = conn.execute(
        "SELECT id FROM students WHERE name=? AND class_id=?",
        (name, class_id)
    ).fetchall()
    if len(rows) == 1:
        return rows[0]["id"]
    if len(rows) > 1 and exam_id is not None:
        # 同名同班多条记录：优先选择未参加本次考试的学生，允许合并分散成绩
        candidate_ids = [r["id"] for r in rows]
        placeholders = ",".join(["?"] * len(candidate_ids))
        participated = conn.execute(
            f"SELECT student_id FROM scores WHERE exam_id=? AND student_id IN ({placeholders})",
            (exam_id,) + tuple(candidate_ids)
        ).fetchall()
        participated_ids = {r["student_id"] for r in participated}
        not_participated = [sid for sid in candidate_ids if sid not in participated_ids]
        if not_participated:
            return not_participated[0]
        # 所有同名学生都参加了本次考试，返回None让调用方创建新记录或报冲突
        return None
    if len(rows) > 1:
        return rows[0]["id"]

    return None


def _import_records_into_exam(
    conn,
    records,
    exam_id,
    batch,
    grade_id,
    major_id,
    subject_config: Optional[Dict[str, Dict[str, float]]] = None,
    class_mapping: Optional[Dict[str, int]] = None,
    overwrite_existing: bool = False,
):
    """Import parsed records into an existing exam. Returns (inserted, updated)."""
    class_mapping = class_mapping or {}
    inserted = 0
    updated = 0
    max_prof_max_score = 0.0
    conflicts = []
    unknown_classes = set()

    # 当启用覆盖模式时，不再拦截冲突，而是直接更新已有成绩
    check_conflicts = not overwrite_existing

    for rec in records:
        if not rec["name"]:
            continue

        class_info = _get_existing_class(conn, rec.get("class_name", ""))
        if not class_info:
            # 尝试使用用户提供的班级映射
            mapped_class_id = class_mapping.get(rec.get("class_name", ""))
            if mapped_class_id:
                row = conn.execute(
                    "SELECT id, grade_id, major_id, class_type_id FROM classes WHERE id=?",
                    (mapped_class_id,),
                ).fetchone()
                if row:
                    class_info = dict(row)
        if not class_info:
            raw_class = rec.get("class_name", "")
            if raw_class:
                unknown_classes.add(raw_class)
            continue

        sid = _resolve_student_id(conn, rec, class_info, exam_id=exam_id)
        if sid is None:
            sid = _get_or_create_student(
                conn,
                rec["name"],
                class_info,
                class_info["grade_id"],
                class_info["major_id"],
                student_no=str(rec.get("student_no") or "").strip(),
            )

        new_scores = {}
        subject_map = {
            "chinese_score": "语文",
            "math_score": "数学",
            "english_score": "英语",
            "professional_score": "专业课",
        }
        for db_col, rec_key in subject_map.items():
            val = _num(rec.get(rec_key))
            if val is not None:
                new_scores[db_col] = val

        provided_total = _num(rec.get("总分"))
        prof_scores = rec.get("professional_subject_scores") or {}
        prof_max_score = _calc_professional_max_score(rec, subject_config)
        if prof_max_score > max_prof_max_score:
            max_prof_max_score = prof_max_score

        existing = conn.execute(
            "SELECT id, chinese_score, math_score, english_score, professional_score, total_score FROM scores WHERE student_id=? AND exam_id=?",
            (sid, exam_id),
        ).fetchone()

        if existing:
            # 冲突检测：要写入的字段在已有记录中已存在非空值（覆盖模式跳过检测）
            if check_conflicts:
                conflict_fields = []
                for k, v in new_scores.items():
                    if v is not None and existing[k] is not None and existing[k] != "":
                        conflict_fields.append(subject_map.get(k, k))
                if conflict_fields:
                    conflicts.append({
                        "row_index": rec.get("row_index"),
                        "name": rec["name"],
                        "class_name": rec.get("class_name", ""),
                        "student_no": rec.get("student_no", ""),
                        "exam_id": exam_id,
                        "conflict_fields": conflict_fields,
                        "message": f"学生 {rec['name']} 在本次考试中已有 {','.join(conflict_fields)} 成绩，无法重复导入"
                    })
                    continue

            current = {
                "chinese_score": existing["chinese_score"],
                "math_score": existing["math_score"],
                "english_score": existing["english_score"],
                "professional_score": existing["professional_score"],
            }
            for k, v in new_scores.items():
                current[k] = v

            # 合并时源文件的“总分”只代表本次上传的局部成绩，必须按已合并字段重新计算
            # 同时保留已有记录中的理化生政史地等其它科目分数，避免总分丢失
            old_main_total = sum(
                v or 0 for v in [
                    existing["chinese_score"], existing["math_score"],
                    existing["english_score"], existing["professional_score"]
                ]
            )
            existing_other = max(0, (existing["total_score"] or 0) - old_main_total)
            total = sum(v or 0 for v in current.values()) + existing_other + _other_subject_total(rec)

            if new_scores:
                cols = list(new_scores.keys()) + ["total_score", "professional_max_score"]
                placeholders = ",".join(f"{c}=?" for c in cols)
                values = [new_scores[k] for k in new_scores.keys()] + [total, prof_max_score, sid, exam_id]
                conn.execute(
                    f"UPDATE scores SET {placeholders} WHERE student_id=? AND exam_id=?",
                    values,
                )
                updated += 1
            _save_score_subject_details(conn, existing["id"], prof_scores, subject_config)
        else:
            if provided_total is not None:
                total = provided_total
            else:
                total = _subject_total(rec)

            try:
                cur = conn.execute(
                    """INSERT INTO scores
                    (student_id, exam_id, chinese_score, math_score, english_score, professional_score,
                     total_score, professional_max_score, is_converted, import_batch, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sid, exam_id,
                        new_scores.get("chinese_score"),
                        new_scores.get("math_score"),
                        new_scores.get("english_score"),
                        new_scores.get("professional_score"),
                        total, prof_max_score, 0, batch, now_str()
                    ),
                )
                inserted += 1
                score_id = cur.lastrowid
                _save_score_subject_details(conn, score_id, prof_scores, subject_config)
            except sqlite3.IntegrityError:
                # 并发或状态不一致导致唯一约束冲突，记录为冲突而非静默忽略
                conflicts.append({
                    "row_index": rec.get("row_index"),
                    "name": rec["name"],
                    "class_name": rec.get("class_name", ""),
                    "student_no": rec.get("student_no", ""),
                    "exam_id": exam_id,
                    "conflict_fields": list(subject_map.values()),
                    "message": f"学生 {rec['name']} 在本次考试中已存在成绩记录（并发冲突）"
                })

    # Update exam_subject_configs professional max score based on actual records
    if max_prof_max_score > 0:
        conn.execute(
            """INSERT INTO exam_subject_configs (exam_id, subject_name, max_score)
               VALUES (?, ?, ?)
               ON CONFLICT(exam_id, subject_name) DO UPDATE SET max_score=?""",
            (exam_id, "专业课", max_prof_max_score, max_prof_max_score),
        )

    if unknown_classes:
        raise UnknownClassError(sorted(unknown_classes))

    if conflicts:
        raise ImportConflictError(conflicts)

    return inserted, updated


def _update_statistics(conn):
    """更新班级、年级、专业学生数量统计。"""
    conn.execute("""
        UPDATE classes SET student_count = (SELECT COUNT(*) FROM students WHERE students.class_id = classes.id)
    """)
    conn.execute("""
        UPDATE grades SET student_count = (SELECT COUNT(*) FROM students WHERE students.grade_id = grades.id),
                          class_count = (SELECT COUNT(*) FROM classes WHERE classes.grade_id = grades.id)
    """)
    conn.execute("""
        UPDATE majors SET student_count = (SELECT COUNT(*) FROM students WHERE students.major_id = majors.id)
    """)


def _build_default_subject_config(major_id: Optional[int]):
    """Build default subject config from system standards."""
    config = {}
    with get_db() as conn:
        rows = conn.execute("SELECT subject_name, major_id, max_score FROM subject_standards").fetchall()
    for r in rows:
        if r["major_id"] is None:
            config.setdefault(r["subject_name"], {"max_score": r["max_score"]})
        elif r["major_id"] == major_id:
            config[r["subject_name"]] = {"max_score": r["max_score"]}
    # Ensure core subjects exist
    for subj, default in [("语文", 150), ("数学", 150), ("英语", 100), ("专业课", 100)]:
        if subj not in config:
            config[subj] = {"max_score": default}
    return config


def _save_exam_subject_configs(conn, exam_id: int, subject_config: Optional[Dict[str, Dict[str, float]]], major_id: Optional[int]):
    """Save subject full-mark config for an exam."""
    if not subject_config:
        subject_config = _build_default_subject_config(major_id)

    # Normalize and validate
    cleaned = {}
    for name, cfg in subject_config.items():
        if not name or not isinstance(name, str):
            continue
        max_score = cfg.get("max_score") if isinstance(cfg, dict) else cfg
        try:
            max_score = float(max_score)
        except (ValueError, TypeError):
            continue
        if max_score <= 0:
            continue
        cleaned[name] = max_score

    for name, max_score in cleaned.items():
        conn.execute(
            """INSERT INTO exam_subject_configs (exam_id, subject_name, max_score)
               VALUES (?, ?, ?)
               ON CONFLICT(exam_id, subject_name) DO UPDATE SET max_score=?""",
            (exam_id, name, max_score, max_score),
        )


def _save_file_subject_mappings(conn, import_file_id: int, subject_config: Optional[Dict[str, Dict[str, float]]]):
    """Save subject mapping for a file to support re-import and auditing."""
    if not subject_config:
        return

    # 先清空旧映射
    conn.execute("DELETE FROM file_subject_mappings WHERE import_file_id=?", (import_file_id,))

    type_map = {
        "语文": "chinese",
        "数学": "math",
        "英语": "english",
        "物理": "physics",
        "化学": "chemistry",
        "生物": "biology",
        "政治": "politics",
        "历史": "history",
        "地理": "geography",
        "专业课": "professional",
        "总分": "total",
    }

    for idx, (name, cfg) in enumerate(subject_config.items()):
        if not name or not isinstance(name, str):
            continue
        max_score = cfg.get("max_score") if isinstance(cfg, dict) else cfg
        try:
            max_score = float(max_score)
        except (ValueError, TypeError):
            max_score = None
        subject_type = type_map.get(name, "unknown")
        conn.execute(
            """INSERT INTO file_subject_mappings
               (import_file_id, column_index, column_header, subject_type, subject_name, max_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (import_file_id, idx, name, subject_type, name, max_score),
        )


class ConfirmImport(BaseModel):
    exam_name: str
    exam_date: Optional[str] = None
    school_year: Optional[str] = None
    semester: Optional[str] = None
    month: Optional[int] = None
    merge_exam_id: Optional[int] = None
    subject_config: Optional[Dict[str, Dict[str, float]]] = None
    # 未匹配班级映射：{文件中的班级名: 系统中已有班级的 id}
    class_mapping: Optional[Dict[str, int]] = None
    # 是否覆盖已有成绩（人工确认冲突后使用）
    overwrite_existing: Optional[bool] = False


class BatchFileConfig(BaseModel):
    file_id: int
    exam_name: Optional[str] = None
    # 该文件独有的未匹配班级映射
    class_mapping: Optional[Dict[str, int]] = None
    # 该文件是否覆盖已有成绩
    overwrite_existing: Optional[bool] = False


class ConfirmBatchImport(BaseModel):
    files: List[BatchFileConfig]
    exam_date: Optional[str] = None
    subject_config: Optional[Dict[str, Dict[str, float]]] = None


@router.post("/confirm/{file_id}")
def confirm_import(file_id: int, payload: ConfirmImport):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM import_files WHERE id=?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文件不存在")

    records = _load_records(row)
    if not records:
        raise HTTPException(status_code=400, detail="文件中未解析到成绩记录")

    with get_db() as conn:
        grade_id = row["grade_id"]
        major_id = row["major_id"]
        school_year = payload.school_year or row["school_year"]
        semester = payload.semester or row["semester"]
        month = payload.month if payload.month is not None else row["month"]

        if payload.merge_exam_id:
            exam = conn.execute("SELECT id, name FROM exams WHERE id=?", (payload.merge_exam_id,)).fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="要合并的考试不存在")
            exam_id = exam["id"]
            is_merge = True
        else:
            existing_id = _find_existing_exam(conn, payload.exam_name, row["exam_type"], school_year, semester, month)
            if existing_id:
                exam_id = existing_id
                is_merge = True
            else:
                cur = conn.execute(
                    "INSERT INTO exams (name, exam_type, school_year, semester, month, exam_date, is_imported, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (payload.exam_name, row["exam_type"], school_year, semester, month, payload.exam_date or now_str()[:10], 1, now_str()),
                )
                exam_id = cur.lastrowid
                is_merge = False

        _save_exam_subject_configs(conn, exam_id, payload.subject_config, major_id)
        _save_file_subject_mappings(conn, file_id, payload.subject_config)

        batch = f"{payload.exam_name}_{exam_id}"
        try:
            inserted, updated = _import_records_into_exam(
                conn, records, exam_id, batch, grade_id, major_id,
                subject_config=payload.subject_config,
                class_mapping=payload.class_mapping,
                overwrite_existing=payload.overwrite_existing or False,
            )
        except UnknownClassError as e:
            # 事务会被 get_db 自动回滚
            raise HTTPException(
                status_code=400,
                detail={"message": str(e), "unknown_classes": e.unknown_classes, "code": "UNKNOWN_CLASS"}
            )
        except ImportConflictError as e:
            # 事务会被 get_db 自动回滚
            raise HTTPException(
                status_code=409,
                detail={"message": str(e), "conflicts": e.conflicts, "code": "IMPORT_CONFLICT"}
            )
        _update_statistics(conn)

        conn.execute("UPDATE import_files SET validation_status='已导入' WHERE id=?", (file_id,))
        if not is_merge:
            conn.execute("UPDATE exams SET is_imported=1 WHERE id=?", (exam_id,))

        log_operation("数据导入", f"确认导入 {payload.exam_name}，新增 {inserted} 条，更新 {updated} 条", conn=conn)
        return {"exam_id": exam_id, "inserted": inserted, "updated": updated, "merged": is_merge}


def _build_exam_name_from_file(row: sqlite3.Row) -> str:
    """Generate default exam name from file metadata."""
    parts = [row["school_year"] or "", row["semester"] or ""]
    if row["exam_type"] == "月考" and row["month"]:
        parts.append(f"{row['month']}月")
    if row["exam_type"]:
        parts.append(row["exam_type"])
    return "".join(parts) or "导入考试"


@router.post("/confirm-batch")
def confirm_batch_import(payload: ConfirmBatchImport):
    """Confirm import multiple files; each file becomes its own exam."""
    if not payload.files:
        raise HTTPException(status_code=400, detail="未选择要导入的文件")

    file_ids = [f.file_id for f in payload.files]
    file_name_map = {f.file_id: f.exam_name for f in payload.files}
    file_config_map = {
        f.file_id: {
            "class_mapping": f.class_mapping,
            "overwrite_existing": f.overwrite_existing or False,
        }
        for f in payload.files
    }

    placeholders = ",".join(["?"] * len(file_ids))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM import_files WHERE id IN ({placeholders})",
            file_ids,
        ).fetchall()
        if len(rows) != len(file_ids):
            raise HTTPException(status_code=404, detail="部分文件不存在")

    # 覆盖模式下允许已导入文件重新处理；非覆盖模式仍要求校验通过
    not_ready = [
        r["file_name"] for r in rows
        if r["validation_status"] != "校验通过" and not file_config_map.get(r["id"], {}).get("overwrite_existing", False)
    ]
    if not_ready:
        raise HTTPException(status_code=400, detail=f"以下文件未校验通过：{', '.join(not_ready)}")

    results = []
    total_inserted = 0
    total_updated = 0

    for row in rows:
        records = _load_records(row)
        if not records:
            results.append({
                "file_id": row["id"],
                "file_name": row["file_name"],
                "exam_id": None,
                "exam_name": None,
                "inserted": 0,
                "updated": 0,
                "skipped": True,
                "reason": "未解析到成绩记录",
            })
            continue

        exam_name = file_name_map.get(row["id"]) or _build_exam_name_from_file(row)
        grade_id = row["grade_id"]
        major_id = row["major_id"]
        school_year = row["school_year"]
        semester = row["semester"]
        month = row["month"]
        exam_type = row["exam_type"]

        with get_db() as conn:
            existing_id = _find_existing_exam(conn, exam_name, exam_type, school_year, semester, month)
            if existing_id:
                exam_id = existing_id
                is_merge = True
            else:
                cur = conn.execute(
                    "INSERT INTO exams (name, exam_type, school_year, semester, month, exam_date, is_imported, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (exam_name, exam_type, school_year, semester, month, payload.exam_date or now_str()[:10], 1, now_str()),
                )
                exam_id = cur.lastrowid
                is_merge = False

            _save_exam_subject_configs(conn, exam_id, payload.subject_config, major_id)
            _save_file_subject_mappings(conn, row["id"], payload.subject_config)

            file_config = file_config_map.get(row["id"]) or {}
            batch = f"{exam_name}_{exam_id}"
            try:
                inserted, updated = _import_records_into_exam(
                    conn, records, exam_id, batch, grade_id, major_id,
                    subject_config=payload.subject_config,
                    class_mapping=file_config.get("class_mapping"),
                    overwrite_existing=file_config.get("overwrite_existing", False),
                )
            except UnknownClassError as e:
                # 该文件事务回滚，跳过并记录未知班级
                conn.rollback()
                results.append({
                    "file_id": row["id"],
                    "file_name": row["file_name"],
                    "exam_id": None,
                    "exam_name": exam_name,
                    "inserted": 0,
                    "updated": 0,
                    "skipped": True,
                    "reason": str(e),
                    "unknown_classes": e.unknown_classes,
                })
                continue
            except ImportConflictError as e:
                # 该文件事务回滚，跳过并记录冲突
                conn.rollback()
                results.append({
                    "file_id": row["id"],
                    "file_name": row["file_name"],
                    "exam_id": None,
                    "exam_name": exam_name,
                    "inserted": 0,
                    "updated": 0,
                    "skipped": True,
                    "reason": str(e),
                    "conflicts": e.conflicts,
                })
                continue
            total_inserted += inserted
            total_updated += updated

            _update_statistics(conn)

            conn.execute("UPDATE import_files SET validation_status='已导入' WHERE id=?", (row["id"],))
            if not is_merge:
                conn.execute("UPDATE exams SET is_imported=1 WHERE id=?", (exam_id,))
            log_operation("数据导入", f"确认导入 {exam_name}，新增 {inserted} 条，更新 {updated} 条", conn=conn)

        results.append({
            "file_id": row["id"],
            "file_name": row["file_name"],
            "exam_id": exam_id,
            "exam_name": exam_name,
            "inserted": inserted,
            "updated": updated,
            "merged": is_merge,
        })

    log_operation("数据导入", f"批量确认导入 {len(results)} 个文件，新增 {total_inserted} 条，更新 {total_updated} 条")
    return {
        "results": results,
        "total_inserted": total_inserted,
        "total_updated": total_updated,
        "file_count": len(results),
    }


@router.delete("/delete/{file_id}")
def delete_import_file(file_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT file_path FROM import_files WHERE id=?", (file_id,)).fetchone()
        if row and row["file_path"]:
            try:
                Path(row["file_path"]).unlink(missing_ok=True)
            except Exception as e:
                # 文件删除失败不影响数据库记录清理，但记录日志便于排查
                log_operation("数据导入", f"删除上传文件失败 id={file_id} path={row['file_path']}：{e}", status="警告", conn=conn)
        conn.execute("DELETE FROM import_files WHERE id=?", (file_id,))
        conn.commit()
    return {"deleted": file_id}
