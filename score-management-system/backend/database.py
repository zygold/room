"""SQLite database initialization and connection helpers."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import BASE_DIR, DATA_DIR, DB_PATH

DATA_DIR.mkdir(exist_ok=True)

SCHEMA_SQL = """
-- 年级表
CREATE TABLE IF NOT EXISTS grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    student_count INTEGER DEFAULT 0,
    class_count INTEGER DEFAULT 0,
    status TEXT DEFAULT '在读',
    created_at TEXT NOT NULL
);

-- 专业表
CREATE TABLE IF NOT EXISTS majors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    student_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- 班级类别表
CREATE TABLE IF NOT EXISTS class_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1
);

-- 班级表
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    grade_id INTEGER NOT NULL,
    major_id INTEGER NOT NULL,
    class_type_id INTEGER NOT NULL,
    student_count INTEGER DEFAULT 0,
    head_teacher TEXT,
    FOREIGN KEY (grade_id) REFERENCES grades(id),
    FOREIGN KEY (major_id) REFERENCES majors(id),
    FOREIGN KEY (class_type_id) REFERENCES class_types(id)
);

-- 学生表
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_no TEXT,                       -- 学号/准考证号（下学期强制）
    name TEXT NOT NULL,
    grade_id INTEGER NOT NULL,
    major_id INTEGER NOT NULL,
    class_type_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    homeroom_teacher TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (grade_id) REFERENCES grades(id) ON DELETE CASCADE,
    FOREIGN KEY (major_id) REFERENCES majors(id) ON DELETE CASCADE,
    FOREIGN KEY (class_type_id) REFERENCES class_types(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

-- 考试表
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    exam_type TEXT NOT NULL,
    grade_id INTEGER,
    major_id INTEGER,
    school_year TEXT,
    semester TEXT,
    month INTEGER,
    exam_date TEXT,
    is_imported INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (grade_id) REFERENCES grades(id),
    FOREIGN KEY (major_id) REFERENCES majors(id)
);

-- 学科分值标准表
CREATE TABLE IF NOT EXISTS subject_standards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT NOT NULL,
    major_id INTEGER,
    max_score REAL NOT NULL,
    pass_score REAL NOT NULL,
    is_fixed INTEGER DEFAULT 0,
    UNIQUE(subject_name, major_id)
);

-- 考试科目满分配置表
CREATE TABLE IF NOT EXISTS exam_subject_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    subject_name TEXT NOT NULL,
    max_score REAL NOT NULL,
    UNIQUE(exam_id, subject_name),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

-- 成绩表
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    chinese_score REAL,
    chinese_converted REAL,
    math_score REAL,
    math_converted REAL,
    english_score REAL,
    english_converted REAL,
    professional_score REAL,
    professional_converted REAL,
    professional_max_score REAL DEFAULT 100,
    total_score REAL,                      -- 原始总分
    total_converted REAL,                  -- 换算后总分
    is_converted INTEGER DEFAULT 0,
    import_batch TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(student_id, exam_id),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

-- 成绩专业课明细表
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
);

-- 奖学金评定批次表
CREATE TABLE IF NOT EXISTS scholarship_screen_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    grade_id INTEGER,
    category TEXT,
    class_id INTEGER,
    exam_ids TEXT,
    created_at TEXT NOT NULL
);

-- 奖学金评定表
CREATE TABLE IF NOT EXISTS scholarships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    screen_run_id INTEGER,
    class_id INTEGER,
    average_score REAL,
    language_avg REAL,
    professional_avg REAL,
    grade_rank TEXT,
    major_rank TEXT,
    award_level TEXT,
    review_status TEXT DEFAULT '待复核',
    review_note TEXT,
    reviewed_at TEXT,
    reviewed_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    FOREIGN KEY (screen_run_id) REFERENCES scholarship_screen_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
);

-- 奖学金规则表
CREATE TABLE IF NOT EXISTS scholarship_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    conditions TEXT NOT NULL,
    grade_ids TEXT,
    class_type_ids TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 备份记录表
CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size TEXT,
    description TEXT,
    data_snapshot TEXT,
    is_encrypted INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- 操作日志表
CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    operation_detail TEXT,
    operator TEXT DEFAULT '管理员',
    status TEXT DEFAULT '成功',
    created_at TEXT NOT NULL
);

-- 导入文件表
CREATE TABLE IF NOT EXISTS import_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT,
    grade_id INTEGER,
    major_id INTEGER,
    exam_type TEXT,
    school_year TEXT,
    semester TEXT,
    month INTEGER,
    student_count INTEGER DEFAULT 0,
    validation_status TEXT DEFAULT '待校验',
    duplicate_count INTEGER DEFAULT 0,
    missing_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- 班级标准名称库
CREATE TABLE IF NOT EXISTS class_name_standards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    grade_id INTEGER,
    major_id INTEGER,
    class_type_id INTEGER,
    has_professional INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 班级别名映射表
CREATE TABLE IF NOT EXISTS class_name_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    alias TEXT NOT NULL,
    UNIQUE(alias)
);

-- 文件科目映射表
CREATE TABLE IF NOT EXISTS file_subject_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_file_id INTEGER NOT NULL,
    column_index INTEGER,
    column_header TEXT,
    subject_type TEXT,      -- 'chinese'|'math'|'english'|'professional'|'total'|'ignore'|'metadata'|'unknown'
    subject_name TEXT,
    max_score REAL,
    FOREIGN KEY (import_file_id) REFERENCES import_files(id) ON DELETE CASCADE
);

-- 导出记录表
CREATE TABLE IF NOT EXISTS export_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_type TEXT NOT NULL,
    filter_condition TEXT,
    format TEXT NOT NULL,
    file_path TEXT,
    file_size TEXT,
    options TEXT,
    created_at TEXT NOT NULL
);

-- 系统设置表
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 教师档案表（课表任课教师）
CREATE TABLE IF NOT EXISTS teachers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    subject_group TEXT,
    created_at    TEXT NOT NULL
);

-- 课表映射表：班级×科目×教师，合班标记
CREATE TABLE IF NOT EXISTS timetable_mappings (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id             INTEGER REFERENCES classes(id) ON DELETE CASCADE,
    class_name           TEXT NOT NULL,
    subject_name         TEXT NOT NULL,
    teacher_id           INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    teacher_name         TEXT NOT NULL,
    is_combined          INTEGER NOT NULL DEFAULT 0,
    combined_class_names TEXT,
    school_year          TEXT,
    semester             TEXT,
    source_slot          TEXT,
    created_at           TEXT NOT NULL,
    UNIQUE(class_id, subject_name, teacher_id, school_year, semester)
);
CREATE INDEX IF NOT EXISTS idx_ttm_class   ON timetable_mappings(class_id, school_year, semester);
CREATE INDEX IF NOT EXISTS idx_ttm_teacher ON timetable_mappings(teacher_id, school_year, semester);

-- 用户表（登录鉴权）
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt         TEXT NOT NULL,
    display_name TEXT,
    role         TEXT DEFAULT 'admin',
    is_active    INTEGER DEFAULT 1,
    last_login   TEXT,
    created_at   TEXT NOT NULL
);

-- 课表导入批次表
CREATE TABLE IF NOT EXISTS timetable_imports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    class_file_name    TEXT NOT NULL,
    teacher_file_name  TEXT NOT NULL,
    class_file_path    TEXT,
    teacher_file_path  TEXT,
    school_year        TEXT,
    semester           TEXT,
    status             TEXT NOT NULL DEFAULT '待确认',
    saved_count        INTEGER NOT NULL DEFAULT 0,
    unmatched_classes  TEXT,
    created_at         TEXT NOT NULL
);
"""

DEFAULT_DATA_SQL = """
-- 初始化班级类别（与奖学金方案对应）
INSERT OR IGNORE INTO class_types (id, name, description, is_active) VALUES
(1, '升学实验班', '升学实验教学班级', 1),
(2, '职普融通班', '职普融通教学班级', 1),
(3, '本科方向班', '本科方向/特优高考班', 1),
(4, '普高升学班', '普高升学教学班级', 1);

-- 初始化学科分值标准（语数外固定）
INSERT OR IGNORE INTO subject_standards (id, subject_name, major_id, max_score, pass_score, is_fixed) VALUES
(1, '语文', NULL, 150, 90, 1),
(2, '数学', NULL, 150, 90, 1),
(3, '英语', NULL, 100, 60, 1);

-- 初始化规范专业及对应专业课默认分值
-- 注意：汽车维修、旅游服务已分别规范为汽车运用与维修、旅游服务与管理
-- 电子商务、会计事务、机电技术、机械制造技术为已废弃专业，不再初始化
INSERT OR IGNORE INTO majors (id, name, student_count, created_at) VALUES
(1, '计算机应用', 0, ?),
(2, '汽车运用与维修', 0, ?),
(3, '幼儿保育', 0, ?),
(4, '数控技术应用', 0, ?),
(5, '旅游服务与管理', 0, ?),
(6, '电子技术应用', 0, ?),
(7, '运动训练', 0, ?);

INSERT OR IGNORE INTO subject_standards (subject_name, major_id, max_score, pass_score, is_fixed) VALUES
('专业课', 1, 100, 60, 0),
('专业课', 2, 100, 60, 0),
('专业课', 3, 100, 60, 0),
('专业课', 4, 100, 60, 0),
('专业课', 5, 100, 60, 0),
('专业课', 6, 100, 60, 0),
('专业课', 7, 100, 60, 0);

-- 默认年级
INSERT OR IGNORE INTO grades (id, name, student_count, class_count, status, created_at) VALUES
(1, '2024级', 0, 0, '在读', ?),
(2, '2025级', 0, 0, '在读', ?),
(3, '2026级', 0, 0, '在读', ?),
(4, '2023级', 0, 0, '在读', ?),
(5, '2022级', 0, 0, '在读', ?);

-- 默认设置

-- 默认管理员 (admin / admin123)
INSERT OR IGNORE INTO users (username, password_hash, salt, display_name, role, is_active, created_at)
VALUES (
    'admin',
    '8f0e32a0f5e4b44a2c7f6a2f3b0b9c1d8e5f2a1b9c3d4e5f6a7b8c9d0e1f2a3',
    'jx2024salt',
    '系统管理员',
    'admin',
    1,
    ?
);

INSERT OR IGNORE INTO settings (key, value) VALUES
('app_password_hash', ''),
('export_desensitize', 'false'),
('operation_log_enabled', 'true'),
('offline_mode', 'true'),
('backup_on_close', 'true'),
('backup_after_import', 'true'),
('backup_retention_days', '30');
"""


def _infer_class_type_id(name: str) -> int:
    """根据班级名称推断奖学金方案对应的班级类别。"""
    if "融通" in name:
        return 2  # 职普融通班
    if "特优" in name or "本方" in name:
        return 3  # 本科方向班
    return 1  # 普通升学班


def sync_class_type_mapping(conn):
    """同步班级类别名称，并按班级名称修正 classes/students 的 class_type_id。
    注意：本函数不管理事务，由调用方统一提交。"""
    # 与奖学金方案名称对齐
    conn.execute(
        "UPDATE OR IGNORE class_types SET name='升学实验班', description='升学实验教学班级' WHERE id=1"
    )
    conn.execute(
        "UPDATE OR IGNORE class_types SET name='本科方向班', description='本科方向/特优高考班' WHERE id=3"
    )

    rows = conn.execute("SELECT id, name, class_type_id FROM classes").fetchall()
    for row in rows:
        inferred = _infer_class_type_id(row["name"])
        if inferred != row["class_type_id"]:
            conn.execute(
                "UPDATE classes SET class_type_id=? WHERE id=?",
                (inferred, row["id"]),
            )
            conn.execute(
                "UPDATE students SET class_type_id=? WHERE class_id=?",
                (inferred, row["id"]),
            )


def _normalize_major_names(conn):
    """将历史数据库中的旧专业名称标准化为规范名称。"""
    renames = {
        "汽车维修": "汽车运用与维修",
        "旅游服务": "旅游服务与管理",
    }
    for old_name, new_name in renames.items():
        conn.execute(
            "UPDATE OR IGNORE majors SET name=? WHERE name=?",
            (new_name, old_name),
        )


# 允许的学科标准名称，防止历史脏数据导致页面重复混乱
_STANDARD_SUBJECT_NAMES = {"语文", "数学", "英语", "专业课"}


def _cleanup_subject_standards(conn):
    """清理学科分值标准表中的非标准名称与重复专业课记录。

    规则：
    1. 只保留标准学科名称：语文、数学、英语、专业课
    2. 删除专业不存在或已合并的 major_id 对应的专业课记录
    3. 同一专业只保留最新的（id 最大的）一条专业课记录
    4. 为现有专业补全缺失的专业课默认记录
    """
    # 1. 删除非标准学科名称
    placeholders = ",".join(["?"] * len(_STANDARD_SUBJECT_NAMES))
    conn.execute(
        f"DELETE FROM subject_standards WHERE subject_name NOT IN ({placeholders})",
        list(_STANDARD_SUBJECT_NAMES),
    )

    # 2. 删除 major_id 无效的专业课记录
    conn.execute(
        """DELETE FROM subject_standards
           WHERE subject_name='专业课'
             AND major_id IS NOT NULL
             AND major_id NOT IN (SELECT id FROM majors)"""
    )

    # 3. 每个专业只保留 id 最大的一条专业课记录
    rows = conn.execute(
        """SELECT major_id, MAX(id) as keep_id
           FROM subject_standards
           WHERE subject_name='专业课' AND major_id IS NOT NULL
           GROUP BY major_id"""
    ).fetchall()
    for r in rows:
        conn.execute(
            """DELETE FROM subject_standards
               WHERE subject_name='专业课'
                 AND major_id=?
                 AND id != ?""",
            (r["major_id"], r["keep_id"]),
        )

    # 4. 为每个现有专业补全专业课默认记录
    valid_majors = conn.execute("SELECT id FROM majors ORDER BY id").fetchall()
    for m in valid_majors:
        conn.execute(
            """INSERT OR IGNORE INTO subject_standards
               (subject_name, major_id, max_score, pass_score, is_fixed)
               VALUES (?, ?, 100, 60, 0)""",
            ("专业课", m["id"]),
        )


def init_db():
    """Create tables and seed default data."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
        # Lightweight migrations for existing databases
        migrations = [
            ("import_files", "file_path TEXT"),
            ("scholarships", "award_level TEXT"),
            ("scholarships", "class_id INTEGER"),
            ("scholarships", "language_avg REAL"),
            ("scholarships", "professional_avg REAL"),
            ("exams", "school_year TEXT"),
            ("exams", "semester TEXT"),
            ("exams", "month INTEGER"),
            ("import_files", "school_year TEXT"),
            ("import_files", "semester TEXT"),
            ("import_files", "month INTEGER"),
            ("import_files", "subject_config TEXT"),
            ("students", "student_no TEXT"),
            ("scores", "total_converted REAL"),
            ("scholarships", "screen_run_id INTEGER"),
        ]
        # Ensure score_subject_details table exists for older databases
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
        for table, column in migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
                conn.commit()
            except sqlite3.OperationalError:
                # 列已存在或表不存在均为预期情况，跳过即可
                pass
        now = datetime.now().isoformat(timespec='seconds')
        conn.executescript(DEFAULT_DATA_SQL.replace("?", f"'{now}'"))
        conn.commit()

        # 标准化历史专业名称
        _normalize_major_names(conn)
        conn.commit()

        # 清理学科分值标准脏数据，避免页面出现重复专业课名称
        _cleanup_subject_standards(conn)
        conn.commit()

        # 创建常用查询索引
        index_sql = """
        CREATE INDEX IF NOT EXISTS idx_scores_student_exam ON scores(student_id, exam_id);
        CREATE INDEX IF NOT EXISTS idx_scores_exam ON scores(exam_id);
        CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_id);
        CREATE INDEX IF NOT EXISTS idx_students_name ON students(name);
        CREATE INDEX IF NOT EXISTS idx_students_no ON students(student_no);
        CREATE INDEX IF NOT EXISTS idx_students_grade_type ON students(grade_id, class_type_id);
        CREATE INDEX IF NOT EXISTS idx_scholarships_run ON scholarships(screen_run_id);
        CREATE INDEX IF NOT EXISTS idx_scholarships_exam ON scholarships(exam_id);
        CREATE INDEX IF NOT EXISTS idx_class_aliases_alias ON class_name_aliases(alias);
        CREATE INDEX IF NOT EXISTS idx_file_subject_mappings_file ON file_subject_mappings(import_file_id);
        """
        conn.executescript(index_sql)
        conn.commit()
        sync_class_type_mapping(conn)


@contextmanager
def get_db(autocommit=True):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        if autocommit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
