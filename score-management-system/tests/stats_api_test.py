"""阶段 2 统计模块接口测试。"""
import json
import sys
from datetime import datetime
from pathlib import Path

# 让测试文件能找到 backend 下的 config/database/main
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
from fastapi.testclient import TestClient


_NOW = datetime.now().isoformat(timespec="seconds")


def _seed_lookup_data(conn):
    """插入年级、专业、班级类别、班级、学科标准等基础数据。"""
    conn.execute(
        "INSERT OR IGNORE INTO grades (name, student_count, class_count, status, created_at) VALUES (?, 0, 0, '在读', ?)",
        ("2025级", _NOW),
    )
    grade_id = conn.execute("SELECT id FROM grades WHERE name=?", ("2025级",)).fetchone()["id"]

    for major_name in ("电子", "计算机"):
        conn.execute(
            "INSERT OR IGNORE INTO majors (name, student_count, created_at) VALUES (?, 0, ?)",
            (major_name, _NOW),
        )
    major_e = conn.execute("SELECT id FROM majors WHERE name=?", ("电子",)).fetchone()["id"]
    major_c = conn.execute("SELECT id FROM majors WHERE name=?", ("计算机",)).fetchone()["id"]

    conn.execute(
        "INSERT OR IGNORE INTO class_types (name, description, is_active) VALUES (?, ?, 1)",
        ("普通班", "普通班"),
    )
    ct_id = conn.execute("SELECT id FROM class_types WHERE name=?", ("普通班",)).fetchone()["id"]

    for cls_name in ("25级电子1班", "25级电子2班"):
        conn.execute(
            """INSERT OR IGNORE INTO classes
               (name, grade_id, major_id, class_type_id, student_count)
               VALUES (?, ?, ?, ?, 0)""",
            (cls_name, grade_id, major_e, ct_id),
        )
    c1 = conn.execute("SELECT id FROM classes WHERE name=?", ("25级电子1班",)).fetchone()["id"]
    c2 = conn.execute("SELECT id FROM classes WHERE name=?", ("25级电子2班",)).fetchone()["id"]

    for subject_name, max_score, pass_score in (
        ("语文", 150, 90),
        ("数学", 150, 90),
        ("英语", 100, 60),
        ("专业课", 100, 60),
    ):
        conn.execute(
            "INSERT OR IGNORE INTO subject_standards (subject_name, major_id, max_score, pass_score) VALUES (?, NULL, ?, ?)",
            (subject_name, max_score, pass_score),
        )

    return grade_id, major_e, major_c, ct_id, c1, c2


def _seed_students(conn, c1, c2, grade_id, major_id, class_type_id):
    """为两个班级分别插入 4 人和 3 人，返回学生 id 列表。"""
    students = [
        ("25E101", "张一", c1, "张老师"),
        ("25E102", "张二", c1, "张老师"),
        ("25E103", "张三", c1, "张老师"),
        ("25E104", "张四", c1, "张老师"),
        ("25E201", "李一", c2, "李老师"),
        ("25E202", "李二", c2, "李老师"),
        ("25E203", "李三", c2, "李老师"),
    ]
    ids = []
    for student_no, name, class_id, homeroom in students:
        cur = conn.execute(
            """INSERT INTO students
               (student_no, name, grade_id, major_id, class_type_id, class_id, homeroom_teacher, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (student_no, name, grade_id, major_id, class_type_id, class_id, homeroom, _NOW),
        )
        ids.append(cur.lastrowid)
    return ids


def _seed_exam_scores_and_mappings(client):
    """插入考试、成绩、课表映射，返回考试 id 与班级 id。"""
    import database

    with database.get_db() as conn:
        grade_id, major_e, _major_c, ct_id, c1, c2 = _seed_lookup_data(conn)
        s1, s2, s3, s4, s5, s6, s7 = _seed_students(conn, c1, c2, grade_id, major_e, ct_id)

        cur = conn.execute(
            """INSERT INTO exams
               (name, exam_type, grade_id, major_id, school_year, semester, month, exam_date, is_imported, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            ("2025下学期期中测试", "期中", grade_id, major_e, "2025-2026", "第一学期", None, None, _NOW),
        )
        exam_id = cur.lastrowid

        # 成绩：最后一位学生缺少专业课成绩，用于验证缺考不计入总分参考
        score_rows = [
            (s1, 90, 95, 65, 70),   # 全部及格，总分 320
            (s2, 80, 92, 70, 55),   # 语文、专业课不及格，总分 297
            (s3, 100, 100, 80, 80), # 全部及格，总分 360
            (s4, 85, 90, 70, None), # 缺考专业课，不参与总分参考
            (s5, 60, 70, 50, 60),   # 数学、英语不及格，总分 240
            (s6, 120, 110, 90, 95), # 全部及格，总分 415
            (s7, 88, 89, 59, 58),   # 全部不及格，总分 294
        ]
        for sid, chinese, math, english, professional in score_rows:
            conn.execute(
                """INSERT INTO scores
                   (student_id, exam_id, chinese_score, math_score, english_score,
                    professional_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sid, exam_id, chinese, math, english, professional, _NOW),
            )

        # 教师与课表映射（1 条普通 + 1 条合班）
        for name, group in (("王老师", "语文"), ("李老师", "数学")):
            conn.execute(
                "INSERT OR IGNORE INTO teachers (name, subject_group, created_at) VALUES (?, ?, ?)",
                (name, group, _NOW),
            )
        t1 = conn.execute("SELECT id FROM teachers WHERE name=?", ("王老师",)).fetchone()["id"]
        t2 = conn.execute("SELECT id FROM teachers WHERE name=?", ("李老师",)).fetchone()["id"]

        conn.execute(
            """INSERT INTO timetable_mappings
               (class_id, class_name, subject_name, teacher_id, teacher_name,
                is_combined, combined_class_names, school_year, semester, source_slot, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (c1, "25级电子1班", "语文", t1, "王老师", 0, None, "2025-2026", "第一学期", None, _NOW),
        )
        conn.execute(
            """INSERT INTO timetable_mappings
               (class_id, class_name, subject_name, teacher_id, teacher_name,
                is_combined, combined_class_names, school_year, semester, source_slot, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                c2,
                "25级电子2班",
                "数学",
                t2,
                "李老师",
                1,
                json.dumps(["25级电子1班", "25级电子2班"]),
                "2025-2026",
                "第一学期",
                None,
                _NOW,
            ),
        )

    return exam_id, c1, c2


@pytest.fixture
def client(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    import database
    database.DB_PATH = tmp_path / "test.db"
    database.init_db()
    from main import app
    return TestClient(app)


def test_stats_exams_empty(client):
    """无导入考试时 /api/stats/exams 返回空列表。"""
    resp = client.get("/api/stats/exams")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_stats_subjects(client):
    """预置考试和学科标准后，/api/stats/subjects 返回正确满分与及格线。"""
    exam_id, _c1, _c2 = _seed_exam_scores_and_mappings(client)
    resp = client.get("/api/stats/subjects", params={"exam_id": exam_id})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["exam_id"] == exam_id
    subjects = data["subjects"]
    assert set(subjects.keys()) >= {"语文", "数学", "英语", "专业课"}
    assert subjects["语文"]["full_score"] == 150.0
    assert subjects["语文"]["pass_score"] == 90.0
    assert subjects["数学"]["full_score"] == 150.0
    assert subjects["数学"]["pass_score"] == 90.0
    assert subjects["英语"]["full_score"] == 100.0
    assert subjects["英语"]["pass_score"] == 60.0
    assert subjects["专业课"]["full_score"] == 100.0
    assert subjects["专业课"]["pass_score"] == 60.0


def test_combined_basic(client):
    """2 个班级、4 科成绩，验证参考人数、及格人数、总分及格/人均计算正确。"""
    exam_id, c1, c2 = _seed_exam_scores_and_mappings(client)
    resp = client.post(
        "/api/stats/combined",
        json={
            "exam_id": exam_id,
            "class_ids": [c1, c2],
            "subject_ids": ["语文", "数学", "英语", "专业课"],
            "total_pass_line": 300,
            "school_year": "2025-2026",
            "semester": "第一学期",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    items = {item["class_id"]: item for item in data["items"]}
    assert set(items.keys()) == {c1, c2}

    # 班级 1：4 人参考，其中 1 人缺考专业课
    item1 = items[c1]
    assert item1["class_name"] == "25级电子1班"
    assert item1["homeroom_teacher"] == "张老师"
    assert item1["total"]["参考"] == 3  # 全科有效的学生数
    assert item1["subject_stats"]["语文"]["参考"] == 4
    assert item1["subject_stats"]["数学"]["参考"] == 4
    assert item1["subject_stats"]["英语"]["参考"] == 4
    assert item1["subject_stats"]["专业课"]["参考"] == 3  # 缺考 1 人
    assert item1["subject_stats"]["语文"]["及格"] == 2
    assert item1["subject_stats"]["数学"]["及格"] == 4
    assert item1["subject_stats"]["英语"]["及格"] == 4
    assert item1["subject_stats"]["专业课"]["及格"] == 2
    # 总分及格：320、297、360 中 >=300 的有 2 人，人均 (320+360)/2
    assert item1["total"]["总分及格"] == 2
    assert item1["total"]["总分人均"] == 340.0

    # 班级 2：3 人全部四科有效
    item2 = items[c2]
    assert item2["class_name"] == "25级电子2班"
    assert item2["homeroom_teacher"] == "李老师"
    assert item2["total"]["参考"] == 3
    for subject in ("语文", "数学", "英语", "专业课"):
        assert item2["subject_stats"][subject]["参考"] == 3
    assert item2["subject_stats"]["语文"]["及格"] == 1
    assert item2["subject_stats"]["数学"]["及格"] == 1
    assert item2["subject_stats"]["英语"]["及格"] == 1
    assert item2["subject_stats"]["专业课"]["及格"] == 2
    # 总分及格：240、415、294 中只有 415 及格
    assert item2["total"]["总分及格"] == 1
    assert item2["total"]["总分人均"] == 415.0


def test_combined_default_subjects(client):
    """combined 请求不传 subject_ids 时默认使用四科。"""
    exam_id, c1, c2 = _seed_exam_scores_and_mappings(client)
    resp = client.post(
        "/api/stats/combined",
        json={
            "exam_id": exam_id,
            "class_ids": [c1, c2],
            "total_pass_line": 300,
            "school_year": "2025-2026",
            "semester": "第一学期",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 2
    for item in data["items"]:
        assert set(item["subject_stats"].keys()) == {"语文", "数学", "英语", "专业课"}

    # 关键指标与显式传入四科时一致
    item1 = next(i for i in data["items"] if i["class_id"] == c1)
    assert item1["total"]["参考"] == 3
    assert item1["subject_stats"]["专业课"]["参考"] == 3


def test_class_subject_metrics(client):
    """/api/stats/class-subject 返回单科指标（应考/参考/及格率等）。"""
    exam_id, c1, _c2 = _seed_exam_scores_and_mappings(client)
    resp = client.get(
        "/api/stats/class-subject",
        params={"exam_id": exam_id, "class_id": c1, "subject_id": "语文"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["exam_id"] == exam_id
    assert data["class_id"] == c1
    assert data["subject_id"] == "语文"
    assert data["应考人数"] == 4
    assert data["参考人数"] == 4
    assert data["缺考人数"] == 0
    assert data["平均分"] == 88.75
    assert data["及格率"] == 0.5
    assert data["优秀率"] == 0.0


def test_teachers_view(client):
    """预置 timetable_mappings 后，/api/stats/teachers 返回教师视图。"""
    exam_id, c1, c2 = _seed_exam_scores_and_mappings(client)
    resp = client.get(
        "/api/stats/teachers",
        params={"exam_id": exam_id, "school_year": "2025-2026", "semester": "第一学期"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["exam_id"] == exam_id
    items = data["items"]
    assert len(items) >= 1

    by_name = {item["teacher_name"]: item for item in items}
    assert "李老师" in by_name
    math_teacher = by_name["李老师"]
    math_subject = next(s for s in math_teacher["subjects"] if s["subject_id"] == "数学")
    assert sorted(math_subject["class_ids"]) == sorted([c1, c2])
    # 合班后应考人数为两个班级之和 7 人
    assert math_subject["应考人数"] == 7

    assert "王老师" in by_name
    chinese_teacher = by_name["王老师"]
    chinese_subject = next(s for s in chinese_teacher["subjects"] if s["subject_id"] == "语文")
    assert chinese_subject["class_ids"] == [c1]
