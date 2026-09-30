"""course_settings / course_setting_imports table access — 课程设置."""
import json
import os
from datetime import datetime

from .base import BaseRepository

COURSE_FILE_EXTS = (".xlsx", ".xls", ".xlsm", ".docx", ".pdf")


def _now():
    return datetime.now().isoformat(timespec="seconds")


class CourseSettingImportRepository(BaseRepository):
    """课程设置导入批次访问."""

    table = "course_setting_imports"
    pk = "id"

    def create(self, file_name, file_path, school_year, semester):
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO course_setting_imports "
                "(file_name, file_path, school_year, semester, status, saved_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (file_name, file_path, school_year, semester, "待确认", 0, _now()),
            )
            conn.commit()
            return cur.lastrowid

    def update_status(self, import_id, status, saved_count=0, unmatched=None):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE course_setting_imports SET status=?, saved_count=?, unmatched_classes=? "
                "WHERE id=?",
                (status, saved_count,
                 json.dumps(unmatched or [], ensure_ascii=False), import_id),
            )
            conn.commit()


class CourseSettingRepository(BaseRepository):
    """课程设置访问."""

    table = "course_settings"
    pk = "id"

    def available_source_files(self):
        rows = self.query(
            "SELECT DISTINCT source_file FROM course_settings "
            "WHERE source_file IS NOT NULL AND source_file != '' ORDER BY source_file")
        return [r["source_file"] for r in rows]

    def upsert(self, course_name, class_id, class_name, teacher_name, periods,
               grade_id, source, source_file, school_year, semester,
               status="待确认", note=None, conn=None):
        sql = (
            "INSERT INTO course_settings "
            "(course_name, class_id, class_name, teacher_name, periods, grade_id, "
            " source, source_file, school_year, semester, status, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(course_name, class_name) DO UPDATE SET "
            "class_id=excluded.class_id, teacher_name=excluded.teacher_name, "
            "periods=excluded.periods, grade_id=excluded.grade_id, source=excluded.source, "
            "source_file=excluded.source_file, school_year=excluded.school_year, "
            "semester=excluded.semester, status=excluded.status, note=excluded.note"
        )
        params = (course_name, class_id, class_name, teacher_name, periods, grade_id,
                  source, source_file, school_year, semester, status, note, _now())
        with self._resolve_conn(conn) as c:
            return c.execute(sql, params).rowcount

    def list_all(self, school_year=None, semester=None, source=None, status=None, conn=None):
        cond, params = ["1=1"], []
        if school_year:
            cond.append("school_year=?")
            params.append(school_year)
        if semester:
            cond.append("semester=?")
            params.append(semester)
        if source:
            cond.append("source=?")
            params.append(source)
        if status:
            cond.append("status=?")
            params.append(status)
        return self.query(
            "SELECT id, course_name, class_id, class_name, teacher_name, periods, grade_id, "
            "source, source_file, school_year, semester, status, note, created_at "
            "FROM course_settings WHERE " + " AND ".join(cond) +
            " ORDER BY course_name, class_name", tuple(params), conn=conn)

    def delete_by_source_file(self, source_file):
        return self.execute_dml(
            "DELETE FROM course_settings WHERE source_file=?", (source_file,)).rowcount
