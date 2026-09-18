"""UserRepository — 用户表的数据访问层."""
from .base import BaseRepository
from datetime import datetime


class UserRepository(BaseRepository):
    table = "users"
    pk = "id"

    def get_by_username(self, username: str):
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

    def update_last_login(self, user_id: int):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), user_id),
            )
            conn.commit()

    def update_password(self, username: str, new_hash: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (new_hash, username),
            )
            conn.commit()
