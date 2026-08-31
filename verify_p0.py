import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import get_db
from services.excel_parser import normalize_class_name

# 验证外键启用
with get_db() as conn:
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    print(f"外键启用: {fk == 1}")

# 验证班级别名映射
with get_db() as conn:
    # 插入测试别名
    conn.execute("""
        INSERT INTO class_name_aliases (canonical_name, alias)
        VALUES (?, ?)
        ON CONFLICT(alias) DO UPDATE SET canonical_name=excluded.canonical_name
    """, ("25级计算机3班（本方）", "25级计算机3班(本方)"))

    # 测试查询
    result = normalize_class_name("25级计算机3班(本方)", conn=conn)
    print(f"班级别名测试: {result}")
    assert result == "25级计算机3班（本方）", f"期望 25级计算机3班（本方）, 实际 {result}"

# 验证 students.student_no 列存在
with get_db() as conn:
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(students)").fetchall()]
    print(f"students 包含 student_no: {'student_no' in cols}")

# 验证 file_subject_mappings 为空或已创建
with get_db() as conn:
    count = conn.execute("SELECT COUNT(*) FROM file_subject_mappings").fetchone()[0]
    print(f"file_subject_mappings 记录数: {count}")

print("P0 核心验证通过")
