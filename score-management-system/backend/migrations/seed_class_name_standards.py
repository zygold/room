"""将现有班级填充到标准名称库和别名映射表。"""
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from datetime import datetime
from database import get_db
from services.excel_parser import normalize_class_name


def seed():
    with get_db() as conn:
        classes = conn.execute("SELECT id, name, grade_id, major_id, class_type_id FROM classes").fetchall()
        now = datetime.now().isoformat(timespec='seconds')
        
        for c in classes:
            canonical = normalize_class_name(c["name"])
            
            # 插入/更新标准名称库
            conn.execute(
                """INSERT INTO class_name_standards (name, grade_id, major_id, class_type_id, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                   grade_id=excluded.grade_id,
                   major_id=excluded.major_id,
                   class_type_id=excluded.class_type_id""",
                (canonical, c["grade_id"], c["major_id"], c["class_type_id"], now)
            )
            
            # 插入别名映射（原始名称 -> 标准名称）
            if canonical != c["name"]:
                conn.execute(
                    """INSERT INTO class_name_aliases (canonical_name, alias)
                       VALUES (?, ?)
                       ON CONFLICT(alias) DO UPDATE SET canonical_name=excluded.canonical_name""",
                    (canonical, c["name"])
                )
        
        print(f"已填充 {len(classes)} 个班级到标准名称库")


if __name__ == "__main__":
    seed()
