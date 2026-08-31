import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import get_db

with get_db() as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS score_subject_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            score_id INTEGER NOT NULL,
            subject_name TEXT NOT NULL,
            original_score REAL,
            converted_score REAL,
            max_score REAL DEFAULT 100,
            created_at TEXT NOT NULL,
            UNIQUE(score_id, subject_name),
            FOREIGN KEY (score_id) REFERENCES scores(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    print("score_subject_details table ensured")
