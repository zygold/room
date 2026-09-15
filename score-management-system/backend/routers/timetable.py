"""课表导入与映射管理路由（阶段 1）。"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from config import UPLOAD_DIR
from database import get_db
from routers.import_scores import _get_existing_class, _safe_filename
from services import timetable_parser
from utils.common import now_str
from utils.logger import log_operation

router = APIRouter()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class ConfirmTimetable(BaseModel):
    replace: Optional[bool] = False


def _resolve_mappings(content_class: bytes, content_teacher: bytes, conn):
    """解析班级/教师课表并匹配到系统中已有的班级与教师。"""
    names = timetable_parser.teacher_names(content_teacher)
    detailed = timetable_parser.parse_class_timetable_detailed(
        content_class, teacher_names=names
    )
    if not detailed:
        cv = timetable_parser.parse_class_timetable(content_class)
        tv = timetable_parser.parse_teacher_timetable(content_teacher)
        conflicts = timetable_parser.cross_validate(cv, tv)
        return {"conflicts": conflicts, "mappings": [], "unmatched": []}

    mappings, unmatched = [], set()
    for cls_title, subject, teacher_raw, slot in detailed:
        class_info = _get_existing_class(conn, cls_title)
        teacher = timetable_parser.resolve_teacher_prefix(teacher_raw, names)
        if teacher is None:
            unmatched.add(cls_title)
            continue
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
    return {"conflicts": [], "mappings": mappings, "unmatched": sorted(unmatched)}


def _mark_combined(mappings, school_year: str, semester: str):
    """合班识别：同一 (subject, teacher, year, semester) 出现在 ≥2 班级即标为合班。"""
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
                others = [n for n in all_names if n != m["class_name"]]
                m["combined_class_names"] = json.dumps(others, ensure_ascii=False)
            else:
                m["combined_class_names"] = None
    return mappings


def _resolve_teacher(conn, name: str):
    """精确查找教师，不存在则插入（并发安全）。"""
    row = conn.execute("SELECT id FROM teachers WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT OR IGNORE INTO teachers (name, created_at) VALUES (?, ?)",
        (name, now_str()),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute("SELECT id FROM teachers WHERE name=?", (name,)).fetchone()
    return row["id"] if row else None


def _dedupe_mappings(mappings):
    """按 (class_id, subject_name, teacher_name) 去重，保留第一个 slot。"""
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
    """上传班级课表与教师课表，创建待确认导入批次。"""
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

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO timetable_imports
            (class_file_name, teacher_file_name, class_file_path, teacher_file_path,
             school_year, semester, status, saved_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                class_file.filename,
                teacher_file.filename,
                str(class_path),
                str(teacher_path),
                school_year,
                semester,
                "待确认",
                0,
                now_str(),
            ),
        )
        import_id = cur.lastrowid

    log_operation(
        "课表上传",
        f"上传班级课表 {class_file.filename} 与教师课表 {teacher_file.filename}，"
        f"学年 {school_year} 学期 {semester}",
    )
    return {
        "id": import_id,
        "class_file_name": class_file.filename,
        "teacher_file_name": teacher_file.filename,
        "status": "待确认",
    }


@router.post("/preview/{import_id}")
def preview_timetable(import_id: int):
    """预览解析结果：班级匹配、教师匹配、未匹配项与冲突项。"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM timetable_imports WHERE id=?", (import_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="导入批次不存在")

        try:
            class_content = Path(row["class_file_path"]).read_bytes()
            teacher_content = Path(row["teacher_file_path"]).read_bytes()
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"读取上传文件失败：{e}")

        result = _resolve_mappings(class_content, teacher_content, conn)

    return {
        "import_id": import_id,
        "school_year": row["school_year"],
        "semester": row["semester"],
        "mappings": result["mappings"],
        "unmatched": result["unmatched"],
        "conflicts": result["conflicts"],
        "total": len(result["mappings"]),
    }


@router.post("/confirm/{import_id}")
def confirm_timetable(import_id: int, payload: Optional[ConfirmTimetable] = None):
    """确认入库：可选覆盖旧数据，解析教师并写入 timetable_mappings。"""
    payload = payload or ConfirmTimetable()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM timetable_imports WHERE id=?", (import_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="导入批次不存在")

    try:
        class_content = Path(row["class_file_path"]).read_bytes()
        teacher_content = Path(row["teacher_file_path"]).read_bytes()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"读取上传文件失败：{e}")

    school_year = row["school_year"]
    semester = row["semester"]

    with get_db() as conn:
        if payload.replace:
            conn.execute(
                "DELETE FROM timetable_mappings WHERE school_year=? AND semester=?",
                (school_year, semester),
            )

        result = _resolve_mappings(class_content, teacher_content, conn)
        mappings = _dedupe_mappings(result["mappings"])
        mappings = _mark_combined(mappings, school_year, semester)

        saved = 0
        for m in mappings:
            teacher_id = _resolve_teacher(conn, m["teacher_name"])
            cur = conn.execute(
                """INSERT INTO timetable_mappings
                (class_id, class_name, subject_name, teacher_id, teacher_name,
                 is_combined, combined_class_names, school_year, semester,
                 source_slot, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(class_id, subject_name, teacher_id, school_year, semester)
                DO UPDATE SET
                    class_name=excluded.class_name,
                    teacher_name=excluded.teacher_name,
                    is_combined=excluded.is_combined,
                    combined_class_names=excluded.combined_class_names,
                    source_slot=excluded.source_slot""",
                (
                    m["class_id"],
                    m["class_name"],
                    m["subject_name"],
                    teacher_id,
                    m["teacher_name"],
                    m["is_combined"],
                    m["combined_class_names"],
                    school_year,
                    semester,
                    m["slot"],
                    now_str(),
                ),
            )
            saved += cur.rowcount or 0

        conn.execute(
            """UPDATE timetable_imports
               SET status='已入库', saved_count=?, unmatched_classes=?
               WHERE id=?""",
            (saved, json.dumps(result["unmatched"], ensure_ascii=False), import_id),
        )

        # 4) 班主任自动提取（从课表表头"班主任：XXX" 或 班会课程）
        ht_updated = 0
        try:
            ht_map = timetable_parser.extract_head_teachers(
                class_content,
                teacher_names=timetable_parser.teacher_names(teacher_content),
            )
            # 检查 classes 表是否已有 head_teacher 字段（兼容旧 DB）
            col_names = [
                r[1] for r in conn.execute("PRAGMA table_info(classes)").fetchall()
            ]
            has_ht_col = "head_teacher" in col_names
            for cls_name, ht_name in ht_map.items():
                cur2 = conn.execute(
                    "SELECT id FROM classes WHERE name=?", (cls_name,)
                )
                cls_row = cur2.fetchone()
                if cls_row:
                    if has_ht_col:
                        conn.execute(
                            "UPDATE classes SET head_teacher=? WHERE id=?",
                            (ht_name, cls_row[0]),
                        )
                    conn.execute(
                        "UPDATE students SET homeroom_teacher=? WHERE class_id=?",
                        (ht_name, cls_row[0]),
                    )
                    ht_updated += 1
            if ht_updated:
                conn.commit()
        except Exception:
            # 班主任提取失败不应阻塞主流程（课表映射已入库）
            pass

    log_operation(
        "课表确认入库",
        f"导入批次 {import_id} 学年 {school_year} 学期 {semester}，"
        f"保存 {saved} 条映射，未匹配 {len(result['unmatched'])} 个班级，"
        f"自动设置班主任 {ht_updated} 个",
    )
    return {"import_id": import_id, "saved": saved, "unmatched": result["unmatched"],
            "head_teachers_set": ht_updated}


@router.get("/mappings")
def list_mappings(
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    class_id: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
):
    """查询课表映射列表，支持按学年/学期/班级/教师过滤。"""
    conditions = ["1=1"]
    params = []
    if school_year:
        conditions.append("m.school_year=?")
        params.append(school_year)
    if semester:
        conditions.append("m.semester=?")
        params.append(semester)
    if class_id:
        conditions.append("m.class_id=?")
        params.append(class_id)
    if teacher_id:
        conditions.append("m.teacher_id=?")
        params.append(teacher_id)

    sql = f"""SELECT
        m.id, m.class_id, m.subject_name, m.teacher_id,
        m.is_combined, m.combined_class_names, m.school_year,
        m.semester, m.source_slot, m.created_at,
        c.name AS class_name, t.name AS teacher_name
    FROM timetable_mappings m
    JOIN classes c ON c.id = m.class_id
    JOIN teachers t ON t.id = m.teacher_id
    WHERE {' AND '.join(conditions)}
    ORDER BY m.id DESC"""

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


@router.get("/overview")
def overview(
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
):
    """教师 → 科目 → 教学班聚合概览。"""
    conditions = ["1=1"]
    params = []
    if school_year:
        conditions.append("school_year=?")
        params.append(school_year)
    if semester:
        conditions.append("semester=?")
        params.append(semester)

    sql = f"""SELECT teacher_name, subject_name, class_name, is_combined
              FROM timetable_mappings
              WHERE {' AND '.join(conditions)}
              ORDER BY teacher_name, subject_name, class_name"""

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    groups = {}
    for r in rows:
        key = (r["teacher_name"], r["subject_name"])
        entry = groups.setdefault(
            key,
            {
                "teacher_name": r["teacher_name"],
                "subject_name": r["subject_name"],
                "classes": [],
                "is_combined": False,
            },
        )
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
    """按学年/学期删除映射，并将相关导入批次标记为已清除。"""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM timetable_mappings WHERE school_year=? AND semester=?",
            (school_year, semester),
        )
        deleted = cur.rowcount
        conn.execute(
            """UPDATE timetable_imports
               SET status='已清除'
               WHERE school_year=? AND semester=? AND status!='已清除'""",
            (school_year, semester),
        )

    log_operation(
        "课表清除",
        f"删除学年 {school_year} 学期 {semester} 的 {deleted} 条课表映射",
    )
    return {"deleted": deleted}
