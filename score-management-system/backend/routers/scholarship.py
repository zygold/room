"""Scholarship APIs."""
import json
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_db
from services.scholarship_engine import run_screen
from utils.common import now_str
from utils.logger import log_operation

router = APIRouter()


class RuleIn(BaseModel):
    name: str
    conditions: dict
    grade_ids: List[int]
    class_type_ids: List[int]
    is_active: bool = True


@router.get("/rules")
def list_rules():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM scholarship_rules ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@router.post("/rules")
def create_rule(item: RuleIn):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO scholarship_rules (name, conditions, grade_ids, class_type_ids, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (item.name, json.dumps(item.conditions, ensure_ascii=False), ",".join(map(str, item.grade_ids)), ",".join(map(str, item.class_type_ids)),
             1 if item.is_active else 0, now_str()),
        )
        conn.commit()
        return {"id": cur.lastrowid}


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, item: RuleIn):
    with get_db() as conn:
        conn.execute(
            "UPDATE scholarship_rules SET name=?, conditions=?, grade_ids=?, class_type_ids=?, is_active=? WHERE id=?",
            (item.name, json.dumps(item.conditions, ensure_ascii=False), ",".join(map(str, item.grade_ids)), ",".join(map(str, item.class_type_ids)),
             1 if item.is_active else 0, rule_id),
        )
        conn.commit()
        return {"id": rule_id}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM scholarship_rules WHERE id=?", (rule_id,))
        conn.commit()
        return {"deleted": rule_id}


class ScreenPayload(BaseModel):
    grade_id: int
    class_type_ids: List[int]
    exam_ids: List[int]
    category: str
    name: Optional[str] = ""
    class_id: Optional[int] = None
    options: Optional[dict] = {}


@router.post("/run-screen")
def run_screen_endpoint(payload: ScreenPayload):
    try:
        count = run_screen(
            payload.grade_id,
            payload.class_type_ids,
            payload.exam_ids,
            payload.category,
            payload.name,
            payload.class_id,
            payload.options,
        )
        log_operation(
            "奖学金筛选",
            f"年级 id={payload.grade_id} 类别 {payload.category} 班级 {payload.class_id or '全部'} 考试 {payload.exam_ids} 候选 {count} 人",
        )
        return {"candidates": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/candidates")
def list_candidates(
    exam_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    review_status: Optional[str] = Query(None),
    award_level: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    with get_db() as conn:
        sql = """
        SELECT sch.*, st.name as student_name, st.class_id,
               c.name as class_name, g.name as grade_name,
               m.name as major_name, ct.name as class_type_name, e.name as exam_name
        FROM scholarships sch
        JOIN students st ON sch.student_id=st.id
        JOIN classes c ON sch.class_id=c.id
        JOIN grades g ON st.grade_id=g.id
        JOIN majors m ON st.major_id=m.id
        JOIN class_types ct ON st.class_type_id=ct.id
        JOIN exams e ON sch.exam_id=e.id
        WHERE 1=1
        """
        params = []
        if exam_id:
            sql += " AND sch.exam_id=?"
            params.append(exam_id)
        if class_id:
            sql += " AND sch.class_id=?"
            params.append(class_id)
        if review_status:
            sql += " AND sch.review_status=?"
            params.append(review_status)
        if award_level:
            sql += " AND sch.award_level=?"
            params.append(award_level)

        total = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
        sql += " ORDER BY CASE sch.award_level WHEN '一等奖' THEN 1 WHEN '二等奖' THEN 2 WHEN '三等奖' THEN 3 ELSE 4 END, sch.language_avg DESC LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        rows = conn.execute(sql, params).fetchall()
        return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


class ReviewIn(BaseModel):
    review_status: str
    review_note: Optional[str] = ""
    reviewed_by: str = "管理员"


@router.put("/candidates/{candidate_id}/review")
def review_candidate(candidate_id: int, item: ReviewIn):
    with get_db() as conn:
        conn.execute(
            "UPDATE scholarships SET review_status=?, review_note=?, reviewed_at=?, reviewed_by=? WHERE id=?",
            (item.review_status, item.review_note or "", now_str(), item.reviewed_by, candidate_id),
        )
        conn.commit()
        log_operation("奖学金复核", f"候选 id={candidate_id} 标记为 {item.review_status}")
        return {"id": candidate_id}


@router.post("/candidates/batch-confirm")
def batch_confirm(payload: dict):
    ids = payload.get("ids", [])
    with get_db() as conn:
        placeholders = ",".join(["?"] * len(ids))
        conn.execute(
            f"UPDATE scholarships SET review_status='已确认', reviewed_at=?, reviewed_by='管理员' WHERE id IN ({placeholders})",
            [now_str()] + ids,
        )
        conn.commit()
        log_operation("奖学金复核", f"批量确认 {len(ids)} 条候选")
        return {"updated": len(ids)}


@router.put("/candidates/{candidate_id}/special-first-prize")
def special_first_prize(candidate_id: int):
    """将某位候选手动特评为一等奖并确认。"""
    with get_db() as conn:
        conn.execute(
            "UPDATE scholarships SET award_level='一等奖', review_status='已确认', review_note='手动特评一等奖', reviewed_at=?, reviewed_by=? WHERE id=?",
            (now_str(), "管理员", candidate_id),
        )
        conn.commit()
        log_operation("奖学金特评", f"候选 id={candidate_id} 手动特评一等奖")
        return {"id": candidate_id}


class ManualFirstPrizeIn(BaseModel):
    student_id: int
    exam_id: int
    class_id: int
    note: Optional[str] = "手动特评一等奖"


@router.post("/manual-first-prize")
def manual_first_prize(item: ManualFirstPrizeIn):
    """手动添加一名特评一等奖学生。"""
    with get_db() as conn:
        # basic validation
        student = conn.execute("SELECT id, class_id FROM students WHERE id=?", (item.student_id,)).fetchone()
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")
        exam = conn.execute("SELECT id FROM exams WHERE id=?", (item.exam_id,)).fetchone()
        if not exam:
            raise HTTPException(status_code=404, detail="考试不存在")
        class_row = conn.execute("SELECT id FROM classes WHERE id=?", (item.class_id,)).fetchone()
        if not class_row:
            raise HTTPException(status_code=404, detail="班级不存在")

        # try to compute averages from the selected exam
        avg_row = conn.execute(
            """
            SELECT
                AVG(chinese_score + math_score + english_score) AS language_avg,
                AVG(professional_score) AS professional_avg
            FROM scores
            WHERE student_id=? AND exam_id=?
            """,
            (item.student_id, item.exam_id),
        ).fetchone()
        language_avg = avg_row["language_avg"] or 0
        professional_avg = avg_row["professional_avg"] or 0

        cur = conn.execute(
            """
            INSERT INTO scholarships
            (student_id, exam_id, class_id, average_score, language_avg, professional_avg,
             grade_rank, major_rank, award_level, review_status, review_note, reviewed_at, reviewed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.student_id,
                item.exam_id,
                item.class_id,
                round(language_avg + professional_avg, 2),
                round(language_avg, 2),
                round(professional_avg, 2),
                "-",
                "-",
                "一等奖",
                "已确认",
                item.note or "手动特评一等奖",
                now_str(),
                "管理员",
                now_str(),
            ),
        )
        conn.commit()
        log_operation("奖学金特评", f"手动添加学生 id={item.student_id} 为特评一等奖")
        return {"id": cur.lastrowid}


@router.get("/stats")
def scholarship_stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM scholarships").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='待复核'").fetchone()[0]
        confirmed = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='已确认'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM scholarships WHERE review_status='不合格'").fetchone()[0]
        return {"total": total, "pending": pending, "confirmed": confirmed, "rejected": rejected}
