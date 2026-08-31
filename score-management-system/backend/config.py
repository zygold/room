"""Central configuration for the score management backend."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "score_management.db"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"
BACKUP_DIR = BASE_DIR / "backups"

HOST = "127.0.0.1"
PORT = 8000

# CORS: restrict to local development frontends by default.
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
