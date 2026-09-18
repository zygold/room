from .base import BaseRepository


class StatsRepository(BaseRepository):
    table = None
    pk = None

    def update_all_counts(self, conn=None):
        with self._resolve_conn(conn) as conn:
            conn.execute(
                """UPDATE classes SET student_count = (SELECT COUNT(*) FROM students WHERE students.class_id = classes.id)""")
            conn.execute(
                """UPDATE grades SET student_count = (SELECT COUNT(*) FROM students WHERE students.grade_id = grades.id),
                                  class_count = (SELECT COUNT(*) FROM classes WHERE classes.grade_id = grades.id)""")
            conn.execute(
                """UPDATE majors SET student_count = (SELECT COUNT(*) FROM students WHERE students.major_id = majors.id)""")
