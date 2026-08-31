"""System settings APIs: grades, majors, class types, classes, subject standards."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from database import get_db
from config import DB_PATH
from utils.common import now_str

router = APIRouter()


# ========== Grades ==========
class GradeIn(BaseModel):
    name: str
    status: str = "在读"


@router.get("/grades")
def list_grades():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM grades ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/grades")
def create_grade(item: GradeIn):
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO grades (name, status, created_at) VALUES (?, ?, ?)",
                (item.name, item.status, now_str()),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": item.name}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"年级已存在或数据错误: {e}")


@router.put("/grades/{grade_id}")
def update_grade(grade_id: int, item: GradeIn):
    with get_db() as conn:
        conn.execute(
            "UPDATE grades SET name=?, status=? WHERE id=?",
            (item.name, item.status, grade_id),
        )
        conn.commit()
        return {"id": grade_id}


@router.delete("/grades/{grade_id}")
def delete_grade(grade_id: int):
    with get_db() as conn:
        # 先删除关联学生，级联删除成绩与奖学金记录
        conn.execute("DELETE FROM students WHERE grade_id=?", (grade_id,))
        # classes 引用 grades，需在删除年级前清理
        conn.execute("DELETE FROM classes WHERE grade_id=?", (grade_id,))
        conn.execute("DELETE FROM grades WHERE id=?", (grade_id,))
        conn.commit()
        return {"deleted": grade_id}


# ========== Majors ==========
class MajorIn(BaseModel):
    name: str


@router.get("/majors")
def list_majors(grade_id: Optional[int] = None):
    with get_db() as conn:
        if grade_id:
            rows = conn.execute(
                """
                SELECT DISTINCT m.*
                FROM majors m
                JOIN classes c ON c.major_id = m.id
                WHERE c.grade_id = ?
                ORDER BY m.id
                """,
                (grade_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM majors ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/majors")
def create_major(item: MajorIn):
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO majors (name, created_at) VALUES (?, ?)",
                (item.name, now_str()),
            )
            conn.commit()
            # create default professional subject standard for new major
            conn.execute(
                "INSERT OR IGNORE INTO subject_standards (subject_name, major_id, max_score, pass_score, is_fixed) VALUES (?, ?, 100, 60, 0)",
                ("专业课", cur.lastrowid),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": item.name}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"专业已存在或数据错误: {e}")


@router.put("/majors/{major_id}")
def update_major(major_id: int, item: MajorIn):
    with get_db() as conn:
        conn.execute(
            "UPDATE majors SET name=? WHERE id=?", (item.name, major_id)
        )
        conn.commit()
        return {"id": major_id}


@router.delete("/majors/{major_id}")
def delete_major(major_id: int):
    with get_db() as conn:
        # 先删除关联学生，级联删除成绩与奖学金记录
        conn.execute("DELETE FROM students WHERE major_id=?", (major_id,))
        # classes 引用 majors，需在删除专业前清理
        conn.execute("DELETE FROM classes WHERE major_id=?", (major_id,))
        conn.execute("DELETE FROM majors WHERE id=?", (major_id,))
        conn.commit()
        return {"deleted": major_id}


# ========== Class Types ==========
@router.get("/class-types")
def list_class_types(grade_id: Optional[int] = None, major_id: Optional[int] = None):
    with get_db() as conn:
        sql = "SELECT DISTINCT ct.* FROM class_types ct JOIN classes c ON c.class_type_id = ct.id WHERE 1=1"
        params = []
        if grade_id:
            sql += " AND c.grade_id=?"
            params.append(grade_id)
        if major_id:
            sql += " AND c.major_id=?"
            params.append(major_id)
        sql += " ORDER BY ct.id"
        if grade_id or major_id:
            rows = conn.execute(sql, params).fetchall()
        else:
            rows = conn.execute("SELECT * FROM class_types ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.put("/class-types/{ct_id}")
def update_class_type(ct_id: int, is_active: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE class_types SET is_active=? WHERE id=?", (is_active, ct_id)
        )
        conn.commit()
        return {"id": ct_id, "is_active": is_active}


# ========== Students ==========
@router.get("/students")
def list_students(
    class_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    keyword: Optional[str] = None,
):
    with get_db() as conn:
        sql = """
        SELECT st.*, c.name as class_name, g.name as grade_name, m.name as major_name, ct.name as class_type_name
        FROM students st
        JOIN classes c ON st.class_id = c.id
        JOIN grades g ON st.grade_id = g.id
        JOIN majors m ON st.major_id = m.id
        JOIN class_types ct ON st.class_type_id = ct.id
        WHERE 1=1
        """
        params = []
        if class_id:
            sql += " AND st.class_id=?"
            params.append(class_id)
        if grade_id:
            sql += " AND st.grade_id=?"
            params.append(grade_id)
        if keyword:
            sql += " AND st.name LIKE ?"
            params.append(f"%{keyword}%")
        sql += " ORDER BY st.id LIMIT 500"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ========== Classes ==========
class ClassIn(BaseModel):
    name: str
    grade_id: int
    major_id: int
    class_type_id: int


@router.get("/classes")
def list_classes(
    grade_id: Optional[int] = None,
    major_id: Optional[int] = None,
    class_type_id: Optional[int] = None,
):
    with get_db() as conn:
        sql = """
        SELECT c.*, g.name as grade_name, m.name as major_name, ct.name as class_type_name
        FROM classes c
        JOIN grades g ON c.grade_id = g.id
        JOIN majors m ON c.major_id = m.id
        JOIN class_types ct ON c.class_type_id = ct.id
        WHERE 1=1
        """
        params = []
        if grade_id:
            sql += " AND c.grade_id=?"
            params.append(grade_id)
        if major_id:
            sql += " AND c.major_id=?"
            params.append(major_id)
        if class_type_id:
            sql += " AND c.class_type_id=?"
            params.append(class_type_id)
        sql += " ORDER BY c.id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


@router.post("/classes")
def create_class(item: ClassIn):
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO classes (name, grade_id, major_id, class_type_id) VALUES (?, ?, ?, ?)",
                (item.name, item.grade_id, item.major_id, item.class_type_id),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": item.name}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"班级已存在或数据错误: {e}")


@router.put("/classes/{class_id}")
def update_class(class_id: int, item: ClassIn):
    with get_db() as conn:
        conn.execute(
            "UPDATE classes SET name=?, grade_id=?, major_id=?, class_type_id=? WHERE id=?",
            (item.name, item.grade_id, item.major_id, item.class_type_id, class_id),
        )
        conn.commit()
        return {"id": class_id}


@router.delete("/classes/{class_id}")
def delete_class(class_id: int):
    with get_db() as conn:
        # 先删除关联学生，级联删除成绩与奖学金记录；避免旧数据库外键 SET NULL 与 NOT NULL 冲突
        conn.execute("DELETE FROM students WHERE class_id=?", (class_id,))
        conn.execute("DELETE FROM classes WHERE id=?", (class_id,))
        conn.commit()
        return {"deleted": class_id}


# 标准学科名称白名单，与 database._STANDARD_SUBJECT_NAMES 保持一致
_STANDARD_SUBJECT_NAMES = {"语文", "数学", "英语", "专业课"}


# ========== Subject Standards ==========
class StandardIn(BaseModel):
    max_score: float
    pass_score: float
    is_fixed: Optional[int] = None


@router.get("/subject-standards")
def list_subject_standards(major_id: Optional[int] = None):
    with get_db() as conn:
        sql = """
        SELECT s.*, m.name as major_name
        FROM subject_standards s
        LEFT JOIN majors m ON s.major_id = m.id
        WHERE s.subject_name IN (?, ?, ?, ?)
        """
        params = list(_STANDARD_SUBJECT_NAMES)
        if major_id is not None:
            sql += " AND (s.major_id IS NULL OR s.major_id = ?)"
            params.append(major_id)
        sql += " ORDER BY s.is_fixed DESC, s.subject_name, s.major_id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


@router.put("/subject-standards/{std_id}")
def update_subject_standard(std_id: int, item: StandardIn):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM subject_standards WHERE id=?", (std_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="分值标准不存在")
        is_fixed = item.is_fixed if item.is_fixed is not None else row["is_fixed"]
        conn.execute(
            "UPDATE subject_standards SET max_score=?, pass_score=?, is_fixed=? WHERE id=?",
            (item.max_score, item.pass_score, is_fixed, std_id),
        )
        conn.commit()
        return {"id": std_id}


# ========== Settings ==========
@router.get("/settings/security")
def get_security_settings():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('app_password_hash','export_desensitize','operation_log_enabled','offline_mode')"
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}


@router.put("/settings/security")
def update_security_settings(payload: dict):
    with get_db() as conn:
        for key, value in payload.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
                (key, str(value), str(value)),
            )
        conn.commit()
    return {"updated": list(payload.keys())}


@router.get("/settings/info")
def get_system_info():
    import os

    size = os.path.getsize(DB_PATH) if DB_PATH.exists() else 0
    return {
        "version": "1.0.0",
        "db_path": str(DB_PATH),
        "db_size": f"{size / 1024 / 1024:.2f}MB",
    }
