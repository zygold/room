from .base import BaseRepository
from utils.common import now_str


class BackupRepository(BaseRepository):
    table = 'backups'
    pk = 'id'

    def list_all(self) -> list:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM backups ORDER BY id DESC').fetchall()]

    def get_latest_created_at(self) -> str | None:
        with self.get_connection() as conn:
            return conn.execute('SELECT MAX(created_at) FROM backups').fetchone()[0]

    def get_by_id(self, backup_id: int):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM backups WHERE id=?', (backup_id,)).fetchone()
            return dict(row) if row else None

    def delete_record(self, backup_id: int):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM backups WHERE id=?', (backup_id,))
            conn.commit()

def create(self, backup_type, file_path, file_size, description, data_snapshot, is_encrypted, created_at):
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO backups (backup_type, file_path, file_size, description, data_snapshot, is_encrypted, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (backup_type, file_path, file_size, description, data_snapshot, is_encrypted, created_at),
            )
            conn.commit()
            return cur.lastrowid
