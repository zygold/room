"""统计引擎数据适配层与纯函数计算引擎。

本模块为 CJ 成绩管理系统对接 JX 统计引擎：
- T1 数据适配层：load_stat_rows / build_subject_registry / build_course_rows
- T2 统计引擎移植：effective_score / _metrics / class_view / teacher_view / combined_view
"""

import json
import sqlite3


# ---------------------------------------------------------------------------
# T1 数据适配层
# ---------------------------------------------------------------------------

# 主科（宽表）字段与学科名称的对应关系
_CORE_SUBJECTS = [
    ("chinese_score", "chinese_converted", "语文"),
    ("math_score", "math_converted", "数学"),
    ("english_score", "english_converted", "英语"),
    ("professional_score", "professional_converted", "专业课"),
]

_DEFAULT_MAX_SCORES = {
    "语文": 150,
    "数学": 150,
    "英语": 100,
    "专业课": 100,
}

_DEFAULT_PASS_RATIO = 0.6


def _to_float(value):
    """将数据库值转换为 float 或 None。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_stat_rows(conn: sqlite3.Connection, exam_id: int, use_converted: bool = False):
    """加载指定考试的成绩行数据，并构建学科注册表。

    返回 (rows, subject_registry)。
    rows 中每行包含：
      class_id, student_id, subject_id, subject_name, score, score_status, exam_score
    subject_registry 格式：
      {subject_id: {"full_score": float, "pass_ratio": float, "pass_score": float}}
    """
    subject_registry = build_subject_registry(conn, exam_id)

    sql = """
        SELECT s.id AS score_id,
               s.student_id,
               s.chinese_score, s.chinese_converted,
               s.math_score, s.math_converted,
               s.english_score, s.english_converted,
               s.professional_score, s.professional_converted,
               st.class_id,
               c.name AS class_name
        FROM scores s
        JOIN students st ON st.id = s.student_id
        JOIN classes c ON c.id = st.class_id
        WHERE s.exam_id = ?
    """
    score_rows = conn.execute(sql, (exam_id,)).fetchall()

    rows = []
    score_ids = []
    for r in score_rows:
        score_ids.append(r["score_id"])
        class_id = r["class_id"]
        student_id = r["student_id"]

        for raw_col, conv_col, subject_id in _CORE_SUBJECTS:
            col = conv_col if use_converted else raw_col
            score = _to_float(r[col])
            rows.append({
                "class_id": class_id,
                "student_id": student_id,
                "subject_id": subject_id,
                "subject_name": subject_id,
                "score": score,
                "score_status": "缺考" if score is None else "正常",
                "exam_score": None,
            })

    # 追加专业课明细长表数据
    if score_ids:
        placeholders = ",".join(["?"] * len(score_ids))
        details = conn.execute(
            f"""SELECT score_id, subject_name, original_score, converted_score
                FROM score_subject_details
                WHERE score_id IN ({placeholders})""",
            tuple(score_ids),
        ).fetchall()

        # 建立 score_id -> class_id/student_id 的映射
        score_meta = {}
        for r in score_rows:
            score_meta[r["score_id"]] = {
                "class_id": r["class_id"],
                "student_id": r["student_id"],
            }

        for d in details:
            meta = score_meta.get(d["score_id"], {})
            subject_name = d["subject_name"]
            score_col = "converted_score" if use_converted else "original_score"
            score = _to_float(d[score_col])
            rows.append({
                "class_id": meta.get("class_id"),
                "student_id": meta.get("student_id"),
                "subject_id": subject_name,
                "subject_name": subject_name,
                "score": score,
                "score_status": "缺考" if score is None else "正常",
                "exam_score": None,
            })

    return rows, subject_registry


def build_subject_registry(conn: sqlite3.Connection, exam_id: int):
    """根据考试科目配置和学科标准构建学科注册表。"""
    # 1. 默认配置
    registry = {}
    for subject_id, max_score in _DEFAULT_MAX_SCORES.items():
        registry[subject_id] = {
            "full_score": float(max_score),
            "pass_ratio": _DEFAULT_PASS_RATIO,
            "pass_score": float(max_score) * _DEFAULT_PASS_RATIO,
        }

    # 2. 收集与本次考试相关的 major_id（学生所属专业）
    exam_major_rows = conn.execute(
        "SELECT major_id FROM exams WHERE id = ?", (exam_id,)
    ).fetchall()
    exam_major_id = exam_major_rows[0]["major_id"] if exam_major_rows else None

    student_major_rows = conn.execute(
        """SELECT DISTINCT st.major_id
           FROM scores s
           JOIN students st ON st.id = s.student_id
           WHERE s.exam_id = ? AND st.major_id IS NOT NULL""",
        (exam_id,),
    ).fetchall()
    related_major_ids = {r["major_id"] for r in student_major_rows}
    if exam_major_id is not None:
        related_major_ids.add(exam_major_id)

    # 3. 学科标准（按专业优先，通用兜底）
    standards_rows = conn.execute(
        "SELECT subject_name, major_id, max_score, pass_score FROM subject_standards"
    ).fetchall()

    def _standards_key(subject_name, major_id):
        return (subject_name, major_id)

    standards_by_major = {}
    standards_general = {}
    for r in standards_rows:
        name = r["subject_name"]
        mid = r["major_id"]
        if mid is None:
            standards_general[name] = r
        else:
            standards_by_major[_standards_key(name, mid)] = r

    def _apply_standard(subject_name, max_score=None):
        """按优先顺序应用学科标准：专业特定 > 通用 > 使用传入的 max_score 与默认比例。"""
        # 专业特定
        for mid in related_major_ids:
            r = standards_by_major.get(_standards_key(subject_name, mid))
            if r is not None:
                return _make_registry_entry(r["max_score"], r["pass_score"])
        # 通用
        r = standards_general.get(subject_name)
        if r is not None:
            return _make_registry_entry(r["max_score"], r["pass_score"])
        # 使用 exam_subject_configs 的 max_score
        if max_score is not None:
            return _make_registry_entry(max_score, None)
        # 默认
        return None

    def _make_registry_entry(max_score, pass_score):
        max_score = float(max_score) if max_score is not None else 100.0
        if pass_score is not None:
            pass_score = float(pass_score)
            pass_ratio = pass_score / max_score if max_score else _DEFAULT_PASS_RATIO
        else:
            pass_ratio = _DEFAULT_PASS_RATIO
            pass_score = max_score * pass_ratio
        return {
            "full_score": max_score,
            "pass_ratio": pass_ratio,
            "pass_score": round(pass_score, 2),
        }

    # 4. 考试科目配置（优先级最高）
    config_rows = conn.execute(
        "SELECT subject_name, max_score FROM exam_subject_configs WHERE exam_id = ?",
        (exam_id,),
    ).fetchall()
    config_names = {r["subject_name"] for r in config_rows}

    # 先应用 exam_subject_configs
    for r in config_rows:
        name = r["subject_name"]
        entry = _apply_standard(name, max_score=r["max_score"])
        if entry is None:
            entry = _make_registry_entry(r["max_score"], None)
        registry[name] = entry

    # 对标准主科和与本次考试相关的专业课，如果没有被配置覆盖，再应用标准
    for subject_id in ("语文", "数学", "英语", "专业课"):
        if subject_id not in registry:
            entry = _apply_standard(subject_id)
            if entry is not None:
                registry[subject_id] = entry

    # 5. 补充专业课明细中涉及的科目（用通用标准或默认值）
    detail_rows = conn.execute(
        """SELECT DISTINCT d.subject_name
           FROM score_subject_details d
           JOIN scores s ON s.id = d.score_id
           WHERE s.exam_id = ?""",
        (exam_id,),
    ).fetchall()
    for r in detail_rows:
        name = r["subject_name"]
        if name not in registry:
            entry = _apply_standard(name)
            if entry is None:
                entry = _make_registry_entry(100.0, None)
            registry[name] = entry

    return registry


def build_course_rows(conn: sqlite3.Connection, school_year: str, semester: str):
    """根据课表映射构建 course_rows，用于 teacher_view。

    返回 [{teacher_id, teacher_name, class_id, subject_id, combined_class_ids}, ...]
    """
    # 先建立班级名到 id 的映射
    class_map = {
        r["name"]: r["id"]
        for r in conn.execute("SELECT id, name FROM classes").fetchall()
    }

    mappings = conn.execute(
        """SELECT class_id, class_name, subject_name, teacher_id, teacher_name,
                  is_combined, combined_class_names
           FROM timetable_mappings
           WHERE school_year = ? AND semester = ?""",
        (school_year, semester),
    ).fetchall()

    course_rows = []
    for m in mappings:
        combined_class_ids = []
        if m["is_combined"] and m["combined_class_names"]:
            try:
                names = json.loads(m["combined_class_names"])
                if isinstance(names, list):
                    for name in names:
                        cid = class_map.get(name)
                        if cid is not None and cid != m["class_id"]:
                            combined_class_ids.append(cid)
            except (json.JSONDecodeError, TypeError):
                # 尝试按逗号分隔的朴素方式兜底
                for name in str(m["combined_class_names"]).split(","):
                    name = name.strip()
                    if not name:
                        continue
                    cid = class_map.get(name)
                    if cid is not None and cid != m["class_id"]:
                        combined_class_ids.append(cid)

        course_rows.append({
            "teacher_id": m["teacher_id"],
            "teacher_name": m["teacher_name"],
            "class_id": m["class_id"],
            "subject_id": m["subject_name"],
            "combined_class_ids": combined_class_ids,
        })

    return course_rows


# ---------------------------------------------------------------------------
# T2 统计引擎移植（保持与 JX stats.py 语义一致）
# ---------------------------------------------------------------------------

def effective_score(r):
    """有效分数：补考按补考分参与及格判定。"""
    if r["score_status"] == "补考" and r.get("exam_score") is not None:
        return r["exam_score"]
    return r["score"]


def _metrics(pool, full_score, pass_ratio):
    if not pool:
        return {"应考人数": 0, "参考人数": 0, "缺考人数": 0,
                "平均分": 0.0, "及格率": 0.0, "优秀率": 0.0}
    pass_line = full_score * pass_ratio
    excellent_line = full_score * 0.8
    scores = [effective_score(r) for r in pool if r["score_status"] in ("正常", "补考")]
    ok = [s for s in scores if s is not None and s >= pass_line]
    good = [s for s in scores if s is not None and s >= excellent_line]
    n = len(scores)
    return {
        "应考人数": len(pool),
        "参考人数": n,
        "缺考人数": sum(1 for r in pool if r["score_status"] == "缺考"),
        "平均分": round(sum(scores) / n, 2) if n else 0.0,
        "及格率": round(len(ok) / n, 4) if n else 0.0,
        "优秀率": round(len(good) / n, 4) if n else 0.0,
    }


def class_view(rows, class_id, subject_id, subject_registry):
    pool = [r for r in rows
            if r["class_id"] == class_id and r["subject_id"] == subject_id]
    s = subject_registry[subject_id]
    return _metrics(pool, s["full_score"], s["pass_ratio"])


def teacher_view(rows, course_rows, teacher_id, subject_registry):
    results = []
    for c in [c for c in course_rows if c["teacher_id"] == teacher_id]:
        class_ids = {c["class_id"]} | set(c.get("combined_class_ids") or [])
        pool = [r for r in rows
                if r["class_id"] in class_ids and r["subject_id"] == c["subject_id"]]
        s = subject_registry[c["subject_id"]]
        results.append({"subject_id": c["subject_id"],
                        "class_ids": sorted(class_ids),
                        **_metrics(pool, s["full_score"], s["pass_ratio"])})
    return results


def combined_view(rows, class_id, subject_ids, subject_registry, pass_lines, total_pass_line):
    pool = [r for r in rows
            if r["class_id"] == class_id and r["subject_id"] in subject_ids]
    by_student = {}
    for r in pool:
        by_student.setdefault(r["student_id"], []).append(r)
    subject_stats = {}
    for sid in subject_ids:
        line = pass_lines.get(sid)
        if line is None:
            reg = subject_registry[sid]
            line = reg["full_score"] * reg["pass_ratio"]
        scores = [effective_score(r) for r in pool
                  if r["subject_id"] == sid and r["score_status"] in ("正常", "补考")
                  and effective_score(r) is not None]
        subject_stats[sid] = {"参考": len(scores),
                              "及格": sum(1 for s in scores if s >= line)}
    total_scores = []
    for rs in by_student.values():
        eff = {r["subject_id"]: effective_score(r) for r in rs
               if r["score_status"] in ("正常", "补考")
               and effective_score(r) is not None}
        if set(subject_ids) <= set(eff):
            total_scores.append(sum(eff[s] for s in subject_ids))
    totals = {"参考": len(total_scores), "总分及格": None, "总分人均": None}
    if total_pass_line is not None:
        passed = [t for t in total_scores if t >= total_pass_line]
        totals["总分及格"] = len(passed)
        totals["总分人均"] = round(sum(passed) / len(passed), 2) if passed else 0.0
    return {"应考": len(by_student), "科目统计": subject_stats, "合计": totals}
