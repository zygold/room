from .base import BaseRepository
from utils.common import now_str
import json


class TimetableImportRepository(BaseRepository):
    table = "timetable_imports"
    pk = "id"

    def create(self, class_file_name, teacher_file_name, class_file_path, teacher_file_path, school_year, semester):
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO timetable_imports (class_file_name, teacher_file_name, class_file_path, teacher_file_path, school_year, semester, status, saved_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (class_file_name, teacher_file_name, class_file_path, teacher_file_path, school_year, semester, "待确认", 0, now_str()),
            )
            conn.commit()
            return cur.lastrowid

    def update_status(self, import_id, status, saved_count=0, unmatched=None):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE timetable_imports SET status=?, saved_count=?, unmatched_classes=? WHERE id=?",
                (status, saved_count, json.dumps(unmatched or [], ensure_ascii=False), import_id),
            )
            conn.commit()

    def mark_cleared_by_year_semester(self, school_year, semester):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE timetable_imports SET status='已清除' WHERE school_year=? AND semester=? AND status!='已清除'",
                (school_year, semester),
            )
            conn.commit()


class TimetableMappingRepository(BaseRepository):
    table = "timetable_mappings"
    pk = "id"

    def delete_by_year_semester(self, school_year, semester):
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM timetable_mappings WHERE school_year=? AND semester=?", (school_year, semester))
            conn.commit()
            return cur.rowcount

    def upsert_mapping(self, class_id, class_name, subject_name, teacher_id, teacher_name, is_combined, combined_class_names, school_year, semester, source_slot):
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO timetable_mappings (class_id, class_name, subject_name, teacher_id, teacher_name, is_combined, combined_class_names, school_year, semester, source_slot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(class_id, subject_name, teacher_id, school_year, semester) DO UPDATE SET class_name=excluded.class_name, teacher_name=excluded.teacher_name, is_combined=excluded.is_combined, combined_class_names=excluded.combined_class_names, source_slot=excluded.source_slot",
                (class_id, class_name, subject_name, teacher_id, teacher_name, is_combined, combined_class_names, school_year, semester, source_slot, now_str()),
            )
            conn.commit()
            return cur.rowcount or 0

    def list_with_filters(self, school_year=None, semester=None, class_id=None, teacher_id=None):
        cond = ["1=1"]
        p = []
        if school_year: cond.append("m.school_year=?"); p.append(school_year)
        if semester: cond.append("m.semester=?"); p.append(semester)
        if class_id: cond.append("m.class_id=?"); p.append(class_id)
        if teacher_id: cond.append("m.teacher_id=?"); p.append(teacher_id)
        sql = "SELECT m.id, m.class_id, m.subject_name, m.teacher_id, m.is_combined, m.combined_class_names, m.school_year, m.semester, m.source_slot, m.created_at, c.name AS class_name, t.name AS teacher_name FROM timetable_mappings m JOIN classes c ON c.id = m.class_id JOIN teachers t ON t.id = m.teacher_id WHERE " + " AND ".join(cond) + " ORDER BY m.id DESC"
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(sql, p).fetchall()]

    def list_for_overview(self, school_year=None, semester=None):
        cond = ["1=1"]
        p = []
        if school_year: cond.append("school_year=?"); p.append(school_year)
        if semester: cond.append("semester=?"); p.append(semester)
        sql = "SELECT teacher_name, subject_name, class_name, is_combined FROM timetable_mappings WHERE " + " AND ".join(cond) + " ORDER BY teacher_name, subject_name, class_name"
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(sql, p).fetchall()]


    def batch_get_by_classes_subjects(self, school_year, semester, class_ids, subject_ids):
        if not class_ids or not subject_ids: return []
        with self.get_connection() as conn:
            ph_c = ','.join(['?'] * len(class_ids))
            ph_s = ','.join(['?'] * len(subject_ids))
            rows = conn.execute(
                f"SELECT class_id, subject_name, teacher_name, is_combined FROM timetable_mappings WHERE school_year = ? AND semester = ? AND class_id IN ({ph_c}) AND subject_name IN ({ph_s})",
                (school_year, semester) + tuple(class_ids) + tuple(subject_ids),
            ).fetchall()
            return [dict(r) for r in rows]


    def list_mappings(self, school_year=None, semester=None, conn=None):
        sql = """SELECT class_id, class_name, subject_name, teacher_id, teacher_name,
                  is_combined, combined_class_names FROM timetable_mappings"""
        params = []
        if school_year or semester:
            sql += ' WHERE 1=1'
            if school_year:
                sql += ' AND school_year=?'
                params.append(school_year)
            if semester:
                sql += ' AND semester=?'
                params.append(semester)
        return self._execute_sql(conn, sql, tuple(params))
