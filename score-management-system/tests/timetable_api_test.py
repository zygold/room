"""课表模块阶段 1 接口测试。"""
import io
import json
import sys
from pathlib import Path

# 让测试文件能找到 backend 下的 config/database/main
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
from fastapi.testclient import TestClient


# 真实班级课表(20260604).xlsx 中的 43 个班级 sheet 名，
# 按 backend/services/excel_parser.normalize_class_name 处理后的形态写入 classes 表。
_REAL_CLASS_NAMES = [
    "23级保育2班(特优)班",
    "23级电子3班(特优)班",
    "23级计算机3班(特优)班",
    "23级计算机4班(特优)班",
    "23级数控3班(特优)班",
    "24级保育1班",
    "24级保育2班（本方）",
    "24级茶艺班",
    "24级电子(国防特色)班",
    "24级电子1班",
    "24级电子2班",
    "24级电子3班",
    "24级电子4班（本方）",
    "24级电子5班（本方）",
    "24级计算机1班",
    "24级计算机2班（本方）",
    "24级计算机3班（本方）",
    "24级旅游1班",
    "24级旅游2班（本方）",
    "24级汽车检测班",
    "24级数控1班",
    "24级数控2班",
    "24级数控3班（本方）",
    "24级运动训练班",
    "25级保育1班",
    "25级保育2班（本方）",
    "25级茶艺班",
    "25级电子1班",
    "25级电子2班",
    "25级电子3班",
    "25级电子4班(国防特色)班",
    "25级电子5班（本方）",
    "25级电子职普融通班",
    "25级计算机1班",
    "25级计算机2班",
    "25级计算机3班（本方）",
    "25级计算机职普融通班",
    "25级旅游1班",
    "25级旅游2班（本方）",
    "25级汽车检测班",
    "25级数控1班",
    "25级数控2班（本方）",
    "25级运动训练班",
]


def _infer_class_type_id(name: str) -> int:
    if "融通" in name:
        return 2
    if "特优" in name or "本方" in name:
        return 3
    return 1


def _major_id_for_class(name: str, major_map: dict) -> int:
    for keyword, mid in major_map.items():
        if keyword in name:
            return mid
    raise ValueError(f"无法为班级匹配专业: {name}")


def _seed_classes(conn):
    """在已初始化的数据库中创建真实课表需要的班级。"""
    # 补充真实课表出现但默认未初始化的专业
    extra_majors = ["茶艺", "汽车检测"]
    for m in extra_majors:
        conn.execute(
            "INSERT OR IGNORE INTO majors (name, student_count, created_at) VALUES (?, 0, datetime('now'))",
            (m,),
        )

    rows = conn.execute("SELECT id, name FROM majors").fetchall()
    major_map = {}
    for r in rows:
        n = r["name"]
        if n == "幼儿保育":
            major_map["保育"] = r["id"]
        elif n == "电子技术应用":
            major_map["电子"] = r["id"]
        elif n == "计算机应用":
            major_map["计算机"] = r["id"]
        elif n == "数控技术应用":
            major_map["数控"] = r["id"]
        elif n == "旅游服务与管理":
            major_map["旅游"] = r["id"]
        elif n == "汽车运用与维修":
            major_map["汽车检测"] = r["id"]
        elif n == "运动训练":
            major_map["运动训练"] = r["id"]
        elif n == "茶艺":
            major_map["茶艺"] = r["id"]

    grade_rows = conn.execute("SELECT id, name FROM grades").fetchall()
    grade_map = {}
    for r in grade_rows:
        if r["name"] == "2023级":
            grade_map["23级"] = r["id"]
        elif r["name"] == "2024级":
            grade_map["24级"] = r["id"]
        elif r["name"] == "2025级":
            grade_map["25级"] = r["id"]

    for name in _REAL_CLASS_NAMES:
        grade_prefix = next((p for p in grade_map if name.startswith(p)), None)
        if grade_prefix is None:
            raise ValueError(f"无法为班级匹配年级: {name}")
        grade_id = grade_map[grade_prefix]
        major_id = _major_id_for_class(name, major_map)
        class_type_id = _infer_class_type_id(name)
        conn.execute(
            """INSERT OR IGNORE INTO classes
               (name, grade_id, major_id, class_type_id, student_count)
               VALUES (?, ?, ?, ?, 0)""",
            (name, grade_id, major_id, class_type_id),
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    import database
    database.DB_PATH = tmp_path / "test.db"
    database.init_db()
    # 预置班级：用真实文件中出现过的班级名，至少 43 个
    with database.get_db() as conn:
        _seed_classes(conn)
    from main import app
    return TestClient(app)


def _fixture(name):
    return Path(__file__).with_name("fixtures") / name


def _upload_real_files(client):
    class_path = _fixture("班级课表(20260604).xlsx")
    teacher_path = _fixture("教师课表(20260604).xlsx")
    resp = client.post(
        "/api/timetable/upload",
        files={
            "class_file": (class_path.name, open(class_path, "rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "teacher_file": (teacher_path.name, open(teacher_path, "rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        },
        data={"school_year": "2025-2026", "semester": "下期"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _db_count(client, table: str) -> int:
    import database
    with database.get_db() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_upload_creates_import_record(client):
    """上传双文件 → 201，timetable_imports 1 条。"""
    import_id = _upload_real_files(client)
    assert import_id > 0
    assert _db_count(client, "timetable_imports") == 1


def test_preview_real_files_resolves_most_classes(client):
    """用真实双课表；预置 43 个班级；断言 mappings > 2000、unmatched 为空或仅个别、conflicts == []。"""
    import_id = _upload_real_files(client)
    resp = client.post(f"/api/timetable/preview/{import_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_id"] == import_id
    assert data["total"] > 2000
    assert data["conflicts"] == []
    assert len(data["unmatched"]) <= 3, f"未匹配班级过多: {data['unmatched']}"


def test_confirm_persists_and_idempotent(client):
    """confirm 后 timetable_mappings 行数>0、teachers 已建表、重复 confirm（replace=False）不翻倍。"""
    import_id = _upload_real_files(client)
    resp = client.post(f"/api/timetable/confirm/{import_id}", json={"replace": False})
    assert resp.status_code == 200, resp.text
    first_saved = resp.json()["saved"]
    assert first_saved > 0
    assert _db_count(client, "timetable_mappings") > 0
    assert _db_count(client, "teachers") > 0

    # 再次 confirm，replace=False，不应翻倍
    resp2 = client.post(f"/api/timetable/confirm/{import_id}", json={"replace": False})
    assert resp2.status_code == 200, resp2.text
    second_saved = resp2.json()["saved"]
    # ON CONFLICT DO UPDATE 的 rowcount 会包含被更新的行，因此 saved 不一定为 0；
    # 幂等性的关键是 mappings 总行数不翻倍。
    mappings_after = _db_count(client, "timetable_mappings")
    assert mappings_after == first_saved, f"重复 confirm 导致数据翻倍: {mappings_after} vs {first_saved}"


def test_combined_detected(client):
    """真实文件解析结果中存在 is_combined=1 的映射。"""
    import_id = _upload_real_files(client)
    client.post(f"/api/timetable/confirm/{import_id}", json={"replace": False})
    resp = client.get("/api/timetable/mappings", params={"school_year": "2025-2026", "semester": "下期"})
    assert resp.status_code == 200, resp.text
    mappings = resp.json()
    assert any(m.get("is_combined") == 1 for m in mappings), "未检测到合班映射"


def test_unmatched_class_reported(client):
    """用合成小课表（未登记班级）→ preview.unmatched 命中。"""
    from openpyxl import Workbook

    # 班级课表：含未登记班级
    wb_cls = Workbook()
    ws_cls = wb_cls.active
    ws_cls.title = "99级未知班"
    ws_cls.append(["", "星期一", "星期二", "星期三", "星期四", "星期五"])
    ws_cls.append(["第1节", "语文\n张三", "", "", "", ""])
    cls_bio = io.BytesIO()
    wb_cls.save(cls_bio)
    cls_bytes = cls_bio.getvalue()

    # 教师课表：提供教师名白名单
    wb_tch = Workbook()
    ws_tch = wb_tch.active
    ws_tch.title = "张三"
    ws_tch.append(["", "星期一", "星期二", "星期三", "星期四", "星期五"])
    ws_tch.append(["第1节", "语文\n99级未知班", "", "", "", ""])
    tch_bio = io.BytesIO()
    wb_tch.save(tch_bio)
    tch_bytes = tch_bio.getvalue()

    resp = client.post(
        "/api/timetable/upload",
        files={
            "class_file": ("cls.xlsx", io.BytesIO(cls_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "teacher_file": ("tch.xlsx", io.BytesIO(tch_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        },
        data={"school_year": "2025-2026", "semester": "下期"},
    )
    assert resp.status_code == 200, resp.text
    import_id = resp.json()["id"]

    resp2 = client.post(f"/api/timetable/preview/{import_id}")
    assert resp2.status_code == 200, resp2.text
    data = resp2.json()
    assert any("99级未知" in u for u in data["unmatched"]), f"未命中未登记班级: {data['unmatched']}"


def test_overview_groups_by_teacher(client):
    """overview 返回教师→科目→教学班聚合行。"""
    import_id = _upload_real_files(client)
    client.post(f"/api/timetable/confirm/{import_id}", json={"replace": False})
    resp = client.get("/api/timetable/overview", params={"school_year": "2025-2026", "semester": "下期"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) > 0
    sample = rows[0]
    assert "teacher_name" in sample
    assert "subject_name" in sample
    assert "classes" in sample and isinstance(sample["classes"], list)
    assert "class_count" in sample


def test_delete_clears_semester(client):
    """DELETE 后 mappings 为 0。"""
    import_id = _upload_real_files(client)
    client.post(f"/api/timetable/confirm/{import_id}", json={"replace": False})
    before = _db_count(client, "timetable_mappings")
    assert before > 0

    resp = client.delete("/api/timetable/mappings", params={"school_year": "2025-2026", "semester": "下期"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == before
    assert _db_count(client, "timetable_mappings") == 0
