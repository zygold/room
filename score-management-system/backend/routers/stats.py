"""统计分析 API 路由（阶段 2 统计模块）。

对接 backend/services/stats_engine.py 提供的纯函数统计引擎，
对外暴露考试、学科注册表、班级组合统计、班级单科指标、教师视图 5 个端点。
"""
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from database import get_db
from services.stats_engine import (
    load_stat_rows,
    build_subject_registry,
    build_course_rows,
    class_view,
    teacher_view,
    combined_view,
)
from utils.common import now_str
from utils.logger import log_operation

router = APIRouter()


@router.get("/exams")
def list_exams(
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    exam_type: Optional[str] = Query(None),
):
    """列出可统计的考试（仅返回 is_imported=1 的考试）。"""
    with get_db() as conn:
        sql = """
            SELECT id, name, school_year, semester, exam_type, month, exam_date
            FROM exams
            WHERE is_imported = 1
        """
        params = []
        if school_year:
            sql += " AND school_year = ?"
            params.append(school_year)
        if semester:
            sql += " AND semester = ?"
            params.append(semester)
        if exam_type:
            sql += " AND exam_type = ?"
            params.append(exam_type)
        sql += " ORDER BY exam_date DESC, id DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


@router.get("/subjects")
def get_subjects(exam_id: int = Query(...)):
    """返回指定考试的学科注册表。"""
    with get_db() as conn:
        registry = build_subject_registry(conn, exam_id)
        return {"exam_id": exam_id, "subjects": registry}


class CombinedRequest(BaseModel):
    exam_id: int
    class_ids: List[int] = Field(default_factory=list)
    subject_ids: List[str] = Field(default_factory=list)
    pass_lines: dict = Field(default_factory=dict)
    total_pass_line: Optional[float] = 0
    school_year: Optional[str] = None
    semester: Optional[str] = None


@router.post("/combined")
def post_combined(body: CombinedRequest):
    """组合统计（班级维度）。"""
    with get_db() as conn:
        rows, subject_registry = load_stat_rows(conn, body.exam_id)

        # 未指定 class_ids 时使用所有参与考试的班级
        if body.class_ids:
            class_ids = body.class_ids
        else:
            class_ids = sorted({r["class_id"] for r in rows if r["class_id"] is not None})

        # 未指定 subject_ids 时默认使用四科
        subject_ids = body.subject_ids or ["语文", "数学", "英语", "专业课"]

        # 过滤掉未在注册表中出现的科目，避免 KeyError
        subject_ids = [s for s in subject_ids if s in subject_registry]

        # 0 或 null 视为不统计总分口径
        total_pass_line = body.total_pass_line if body.total_pass_line else None

        # 批量获取班级名称与班主任
        class_map = {}
        homeroom_map = {}
        if class_ids:
            placeholders = ",".join(["?"] * len(class_ids))
            class_rows = conn.execute(
                f"SELECT id, name FROM classes WHERE id IN ({placeholders})",
                tuple(class_ids),
            ).fetchall()
            class_map = {r["id"]: r["name"] for r in class_rows}

            homeroom_rows = conn.execute(
                f"""
                SELECT class_id, homeroom_teacher
                FROM students
                WHERE class_id IN ({placeholders}) AND homeroom_teacher IS NOT NULL AND homeroom_teacher != ''
                GROUP BY class_id
                """,
                tuple(class_ids),
            ).fetchall()
            homeroom_map = {r["class_id"]: r["homeroom_teacher"] for r in homeroom_rows}

        # 批量获取科目教师（含合班标记）
        teacher_map = {}
        if body.school_year and body.semester and class_ids and subject_ids:
            placeholders_cls = ",".join(["?"] * len(class_ids))
            placeholders_subj = ",".join(["?"] * len(subject_ids))
            ttm_rows = conn.execute(
                f"""
                SELECT class_id, subject_name, teacher_name, is_combined
                FROM timetable_mappings
                WHERE school_year = ? AND semester = ?
                  AND class_id IN ({placeholders_cls})
                  AND subject_name IN ({placeholders_subj})
                """,
                (body.school_year, body.semester) + tuple(class_ids) + tuple(subject_ids),
            ).fetchall()
            for r in ttm_rows:
                key = (r["class_id"], r["subject_name"])
                name = r["teacher_name"] or ""
                if r["is_combined"]:
                    name += "（合班）"
                teacher_map[key] = name

        items = []
        for class_id in class_ids:
            raw = combined_view(
                rows,
                class_id,
                subject_ids,
                subject_registry,
                body.pass_lines,
                total_pass_line,
            )
            subject_stats = {}
            for sid in subject_ids:
                stats = raw["科目统计"].get(sid, {"参考": 0, "及格": 0})
                subject_stats[sid] = {
                    "参考": stats["参考"],
                    "及格": stats["及格"],
                    "teacher": teacher_map.get((class_id, sid), ""),
                }

            items.append({
                "class_id": class_id,
                "class_name": class_map.get(class_id, ""),
                "homeroom_teacher": homeroom_map.get(class_id, ""),
                "subject_stats": subject_stats,
                "total": raw["合计"],
            })

        log_operation("统计查询", f"组合统计 exam_id={body.exam_id} 班级数={len(items)}")
        return {"exam_id": body.exam_id, "items": items}


@router.get("/class-subject")
def get_class_subject(
    exam_id: int = Query(...),
    class_id: int = Query(...),
    subject_id: str = Query(...),
):
    """班级单科指标。"""
    with get_db() as conn:
        rows, subject_registry = load_stat_rows(conn, exam_id)
        if subject_id not in subject_registry:
            raise HTTPException(status_code=400, detail=f"未找到学科: {subject_id}")
        metrics = class_view(rows, class_id, subject_id, subject_registry)
        return {
            "exam_id": exam_id,
            "class_id": class_id,
            "subject_id": subject_id,
            **metrics,
        }


@router.get("/teachers")
def get_teachers(
    exam_id: int = Query(...),
    school_year: str = Query(...),
    semester: str = Query(...),
):
    """教师视图。"""
    with get_db() as conn:
        rows, subject_registry = load_stat_rows(conn, exam_id)
        course_rows = build_course_rows(conn, school_year, semester)

        teacher_ids = sorted({c["teacher_id"] for c in course_rows if c["teacher_id"] is not None})
        teacher_names = {c["teacher_id"]: c["teacher_name"] for c in course_rows}

        items = []
        for tid in teacher_ids:
            subjects = teacher_view(rows, course_rows, tid, subject_registry)
            items.append({
                "teacher_id": tid,
                "teacher_name": teacher_names.get(tid, ""),
                "subjects": subjects,
            })

        log_operation("统计查询", f"教师视图 exam_id={exam_id} 教师数={len(items)}")
        return {"exam_id": exam_id, "items": items}
