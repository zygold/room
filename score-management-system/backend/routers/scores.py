"""Score management APIs."""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from database import get_db
from services.score_converter import convert_scores
from utils.common import now_str
from utils.logger import log_operation

router = APIRouter()


SORT_FIELD_MAP = {
    "name": "st.name",
    "student_no": "st.student_no",
    "grade_name": "g.name",
    "major_name": "m.name",
    "class_type_name": "ct.name",
    "class_name": "c.name",
    "exam_name": "e.name",
    "chinese_score": "s.chinese_score",
    "math_score": "s.math_score",
    "english_score": "s.english_score",
    "professional_score": "s.professional_score",
    "total_score": "s.total_score",
    "is_converted": "s.is_converted",
}


@router.get("/")
def list_scores(
    grade_id: Optional[int] = Query(None),
    major_id: Optional[int] = Query(None),
    class_type_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    exam_id: Optional[int] = Query(None),
    exam_type: Optional[str] = Query(None),
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    month: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    is_converted: Optional[int] = Query(None),
    sort_field: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=10000),
):
    with get_db() as conn:
        sql = """
        SELECT s.*, st.name as student_name, st.student_no, st.homeroom_teacher,
               c.name as class_name, g.name as grade_name, m.name as major_name, ct.name as class_type_name,
               e.name as exam_name, e.exam_type, e.exam_date, e.school_year, e.semester, e.month
        FROM scores s
        JOIN students st ON s.student_id = st.id
        JOIN classes c ON st.class_id = c.id
        JOIN grades g ON st.grade_id = g.id
        JOIN majors m ON st.major_id = m.id
        JOIN class_types ct ON st.class_type_id = ct.id
        JOIN exams e ON s.exam_id = e.id
        WHERE 1=1
        """
        params = []
        if grade_id:
            sql += " AND st.grade_id=?"
            params.append(grade_id)
        if major_id:
            sql += " AND st.major_id=?"
            params.append(major_id)
        if class_type_id:
            sql += " AND st.class_type_id=?"
            params.append(class_type_id)
        if class_id:
            sql += " AND st.class_id=?"
            params.append(class_id)
        if exam_id:
            sql += " AND s.exam_id=?"
            params.append(exam_id)
        if exam_type:
            sql += " AND e.exam_type=?"
            params.append(exam_type)
        if school_year:
            sql += " AND e.school_year=?"
            params.append(school_year)
        if semester:
            sql += " AND e.semester=?"
            params.append(semester)
        if month is not None:
            sql += " AND e.month=?"
            params.append(month)
        if is_converted is not None:
            sql += " AND s.is_converted=?"
            params.append(is_converted)
        if keyword:
            sql += " AND st.name LIKE ?"
            params.append(f"%{keyword}%")

        count_sql = f"SELECT COUNT(*) FROM ({sql})"
        total = conn.execute(count_sql, params).fetchone()[0]

        order_col = SORT_FIELD_MAP.get(sort_field, "s.id")
        order_dir = "ASC" if sort_order and sort_order.lower() == "asc" else "DESC"
        sql += f" ORDER BY {order_col} {order_dir}, s.id DESC LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        rows = conn.execute(sql, params).fetchall()
        return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


class ScoreUpdate(BaseModel):
    chinese_score: Optional[float] = None
    math_score: Optional[float] = None
    english_score: Optional[float] = None
    professional_score: Optional[float] = None


@router.put("/{score_id}")
def update_score(score_id: int, item: ScoreUpdate):
    with get_db() as conn:
        score = conn.execute("SELECT * FROM scores WHERE id=?", (score_id,)).fetchone()
        if not score:
            raise HTTPException(status_code=404, detail="成绩不存在")

        updates = []
        values = []
        for field in ["chinese_score", "math_score", "english_score", "professional_score"]:
            val = getattr(item, field)
            if val is not None:
                updates.append(f"{field}=?")
                values.append(val)
        if not updates:
            return {"id": score_id}

        # 重新计算原始总分（基于可编辑主科）
        total_fields = ["chinese_score", "math_score", "english_score", "professional_score"]
        new_total = 0.0
        for field in total_fields:
            val = getattr(item, field)
            if val is None:
                val = score[field]
            try:
                new_total += float(val or 0)
            except (TypeError, ValueError):
                pass
        updates.append("total_score=?")
        values.append(round(new_total, 2))

        # 手动修改后重置换算状态，并清除换算分，避免显示过期换算结果
        if score["is_converted"]:
            updates.extend([
                "is_converted=0",
                "chinese_converted=NULL",
                "math_converted=NULL",
                "english_converted=NULL",
                "professional_converted=NULL",
                "total_converted=NULL",
            ])

        values.append(score_id)
        conn.execute(f"UPDATE scores SET {', '.join(updates)} WHERE id=?", values)
        conn.commit()

    log_operation("成绩修改", f"修改成绩 id={score_id}")
    return {"id": score_id}


class ConvertPayload(BaseModel):
    exam_id: int
    score_ids: Optional[List[int]] = None
    original_max: dict = Field(default_factory=dict)


@router.post("/convert")
def convert_score_endpoint(payload: ConvertPayload):
    updated = convert_scores(payload.exam_id, payload.score_ids, payload.original_max)
    log_operation("分值换算", f"考试 id={payload.exam_id} 换算 {updated} 条成绩")
    return {"updated": updated}


@router.get("/exam-subject-configs/{exam_id}")
def get_exam_subject_configs_endpoint(exam_id: int):
    """Return configured full marks for each subject in an exam."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT subject_name, max_score FROM exam_subject_configs WHERE exam_id=?",
            (exam_id,),
        ).fetchall()
        return {r["subject_name"]: r["max_score"] for r in rows}


class ExamSubjectConfigPayload(BaseModel):
    configs: dict


@router.post("/exam-subject-configs/{exam_id}")
def set_exam_subject_configs_endpoint(exam_id: int, payload: ExamSubjectConfigPayload):
    """Set full marks for each subject in an exam."""
    with get_db() as conn:
        exam = conn.execute("SELECT id FROM exams WHERE id=?", (exam_id,)).fetchone()
        if not exam:
            raise HTTPException(status_code=404, detail="考试不存在")
        for subject_name, max_score in payload.configs.items():
            conn.execute(
                """INSERT INTO exam_subject_configs (exam_id, subject_name, max_score)
                   VALUES (?, ?, ?)
                   ON CONFLICT(exam_id, subject_name) DO UPDATE SET max_score=excluded.max_score""",
                (exam_id, subject_name, max_score),
            )
        conn.commit()
    log_operation("考试科目满分配置", f"考试 id={exam_id} 配置 {len(payload.configs)} 门科目")
    return {"exam_id": exam_id, "configs": payload.configs}


@router.get("/conversion-log")
def conversion_log(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM operation_logs WHERE operation_type='分值换算' ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/exams")
def list_exams(
    school_year: str = None,
    semester: str = None,
    exam_type: str = None,
):
    with get_db() as conn:
        sql = "SELECT * FROM exams WHERE 1=1"
        params = []
        if school_year:
            sql += " AND school_year=?"
            params.append(school_year)
        if semester:
            sql += " AND semester=?"
            params.append(semester)
        if exam_type:
            sql += " AND exam_type=?"
            params.append(exam_type)
        sql += " ORDER BY school_year DESC, semester DESC, month DESC, id DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


@router.delete("/exams/{exam_id}")
def delete_exam(exam_id: int):
    with get_db() as conn:
        exam = conn.execute("SELECT id, name FROM exams WHERE id=?", (exam_id,)).fetchone()
        if not exam:
            raise HTTPException(status_code=404, detail="考试不存在")
        score_count = conn.execute("SELECT COUNT(*) FROM scores WHERE exam_id=?", (exam_id,)).fetchone()[0]
        conn.execute("DELETE FROM scores WHERE exam_id=?", (exam_id,))
        conn.execute("DELETE FROM scholarships WHERE exam_id=?", (exam_id,))
        conn.execute("DELETE FROM exams WHERE id=?", (exam_id,))
        conn.commit()
    log_operation("考试删除", f"删除考试 id={exam_id} {exam['name']} 及 {score_count} 条成绩")
    return {"deleted": exam_id, "score_count": score_count}


class BatchDeletePayload(BaseModel):
    ids: List[int]


@router.delete("/batch")
def batch_delete_scores(payload: BatchDeletePayload):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="未选择要删除的成绩")
    placeholders = ",".join(["?"] * len(payload.ids))
    with get_db() as conn:
        conn.execute(f"DELETE FROM scores WHERE id IN ({placeholders})", list(payload.ids))
        conn.commit()
    log_operation("成绩删除", f"批量删除 {len(payload.ids)} 条成绩")
    return {"deleted": len(payload.ids)}


@router.delete("/batch-by-filter")
def batch_delete_scores_by_filter(
    grade_id: Optional[int] = Query(None),
    major_id: Optional[int] = Query(None),
    class_type_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    exam_id: Optional[int] = Query(None),
    exam_type: Optional[str] = Query(None),
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    month: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    is_converted: Optional[int] = Query(None),
):
    """Delete all score records matching the provided filters."""
    with get_db() as conn:
        sql = """
        SELECT s.id FROM scores s
        JOIN students st ON s.student_id = st.id
        JOIN classes c ON st.class_id = c.id
        JOIN grades g ON st.grade_id = g.id
        JOIN majors m ON st.major_id = m.id
        JOIN class_types ct ON st.class_type_id = ct.id
        JOIN exams e ON s.exam_id = e.id
        WHERE 1=1
        """
        params = []
        if grade_id:
            sql += " AND st.grade_id=?"
            params.append(grade_id)
        if major_id:
            sql += " AND st.major_id=?"
            params.append(major_id)
        if class_type_id:
            sql += " AND st.class_type_id=?"
            params.append(class_type_id)
        if class_id:
            sql += " AND st.class_id=?"
            params.append(class_id)
        if exam_id:
            sql += " AND s.exam_id=?"
            params.append(exam_id)
        if exam_type:
            sql += " AND e.exam_type=?"
            params.append(exam_type)
        if school_year:
            sql += " AND e.school_year=?"
            params.append(school_year)
        if semester:
            sql += " AND e.semester=?"
            params.append(semester)
        if month is not None:
            sql += " AND e.month=?"
            params.append(month)
        if is_converted is not None:
            sql += " AND s.is_converted=?"
            params.append(is_converted)
        if keyword:
            sql += " AND st.name LIKE ?"
            params.append(f"%{keyword}%")

        ids = [r[0] for r in conn.execute(sql, params).fetchall()]
        if not ids:
            return {"deleted": 0}
        deleted = 0
        chunk_size = 500
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            cur = conn.execute(f"DELETE FROM scores WHERE id IN ({placeholders})", chunk)
            deleted += cur.rowcount
        conn.commit()
    log_operation("成绩删除", f"按筛选条件批量删除 {deleted} 条成绩")
    return {"deleted": deleted}


class SubjectDetailsQuery(BaseModel):
    score_ids: List[int]


@router.post("/subject-details")
def get_subject_details(payload: SubjectDetailsQuery):
    """Return professional subject details grouped by score_id."""
    if not payload.score_ids:
        return {}
    placeholders = ",".join(["?"] * len(payload.score_ids))
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT score_id, subject_name, original_score, converted_score
                FROM score_subject_details
                WHERE score_id IN ({placeholders})
                ORDER BY score_id, subject_name""",
            list(payload.score_ids),
        ).fetchall()
    result = {}
    for r in rows:
        result.setdefault(r["score_id"], []).append({
            "subject_name": r["subject_name"],
            "original_score": r["original_score"],
            "converted_score": r["converted_score"],
        })
    return result
