from .base import BaseRepository


class HeadteacherRepository(BaseRepository):
    table = "classes"
    pk = "id"

    def apply_batch(self, matched):
        applied = 0
        with self.get_connection() as conn:
            for item in matched:
                class_id, head_teacher = item[0], item[2]
                conn.execute("UPDATE classes SET head_teacher=? WHERE id=?", (head_teacher, class_id))
                conn.execute("UPDATE students SET homeroom_teacher=? WHERE class_id=?", (head_teacher, class_id))
                applied += 1
            conn.commit()
        return applied
