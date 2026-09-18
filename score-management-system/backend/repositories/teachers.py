"""TeacherRepository — 教师表的数据访问层."""
from .base import BaseRepository
from utils.common import now_str


class TeacherRepository(BaseRepository):
    table = "teachers"
    pk = "id"

    def find_or_create(self, name: str):
        """精确查找教师; 不存在则插入 (并发安全, INSERT OR IGNORE)."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT id FROM teachers WHERE name=?", (name,)).fetchone()
            if row:
                return row["id"]
            cur = conn.execute(
                "INSERT OR IGNORE INTO teachers (name, created_at) VALUES (?, ?)",
                (name, now_str()),
            )
            if cur.lastrowid:
                conn.commit()
                return cur.lastrowid
            # IGNORE 导致没拿到 id, 再查一次
            row = conn.execute("SELECT id FROM teachers WHERE name=?", (name,)).fetchone()
            return row["id"] if row else None
