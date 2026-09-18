from .base import BaseRepository


class SettingsTableRepository(BaseRepository):
    table = 'settings'
    pk = 'key'

    def get_security_settings(self):
        keys = ('app_password_hash', 'export_desensitize', 'operation_log_enabled', 'offline_mode')
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT key, value FROM settings WHERE key IN (?, ?, ?, ?)',
                keys,
            ).fetchall()
            return {r['key']: r['value'] for r in rows}

    def upsert_many(self, payload: dict) -> list:
        with self.get_connection() as conn:
            for key, value in payload.items():
                conn.execute(
                    'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?',
                    (key, str(value), str(value)),
                )
            conn.commit()
        return list(payload.keys())

    def get_by_key_prefix(self, prefix):
        with self.get_connection() as conn:
            rows = conn.execute('SELECT key, value FROM settings WHERE key LIKE ?', (prefix + '%',)).fetchall()
            return {r['key']: r['value'] for r in rows}

    def upsert_many_with_prefix(self, items, prefix):
        with self.get_connection() as conn:
            for key, value in items.items():
                db_key = prefix + key
                if isinstance(value, bool):
                    value = 'true' if value else 'false'
                elif isinstance(value, list):
                    value = ','.join(str(v) for v in value)
                conn.execute(
                    'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?',
                    (db_key, str(value), str(value)),
                )
            conn.commit()
