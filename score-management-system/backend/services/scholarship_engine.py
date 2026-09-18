"""Scholarship screening engine based on the school scheme.

Categories:
- 职普融通班: all eligible students get first prize.
- 本科方向班: based on yearly average of (Chinese+Math+English) and professional subject,
  per grade top 3/6/9 language rank + professional class rank thresholds.
- 普通升学班: based on yearly average of (Chinese+Math+English) and professional subject,
  top 3 language rank in grade + professional major rank top 15.
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from database import get_db
from repositories.base import BaseRepository

_base_repo = BaseRepository()
from repositories.scholarships import ScholarshipRepository

_scholarship_repo = ScholarshipRepository()


def _to_float(v):
    return float(v) if v is not None else 0.0


def _rank_desc(values: List[tuple]) -> Dict[int, int]:
    """Return rank map {student_id: rank} sorted by value descending."""
    sorted_values = sorted(values, key=lambda x: x[1], reverse=True)
    return {sid: (idx + 1) for idx, (sid, _) in enumerate(sorted_values)}


def _fetch_student_averages(conn, grade_id: int, class_type_ids: List[int], exam_ids: List[int], use_converted: bool = False) -> List[dict]:
    placeholders_exams = ",".join(["?"] * len(exam_ids))
    placeholders_types = ",".join(["?"] * len(class_type_ids))
    if use_converted:
        lang_sum = "s.chinese_converted + s.math_converted + s.english_converted"
        prof_col = "s.professional_converted"
    else:
        lang_sum = "s.chinese_score + s.math_score + s.english_score"
        prof_col = "s.professional_score"
    sql = f"""
    SELECT
        st.id AS student_id,
        st.name AS student_name,
        st.class_id,
        st.major_id,
        c.name AS class_name,
        m.name AS major_name,
        g.name AS grade_name,
        AVG({lang_sum}) AS language_avg,
        AVG({prof_col}) AS professional_avg,
        COUNT(s.id) AS exam_count
    FROM students st
    JOIN classes c ON st.class_id = c.id
    JOIN majors m ON st.major_id = m.id
    JOIN grades g ON st.grade_id = g.id
    LEFT JOIN scores s ON s.student_id = st.id AND s.exam_id IN ({placeholders_exams})
    WHERE st.grade_id = ? AND st.class_type_id IN ({placeholders_types})
    GROUP BY st.id
    HAVING exam_count > 0
    """
    params = list(exam_ids) + [grade_id] + list(class_type_ids)
    return _base_repo.query(sql, params, conn=conn, as_dict=False)


def _screen_benkefangxiang(students: List[dict], special_top_language_first_prize: bool = True) -> List[Dict[str, Any]]:
    """本科方向班（特优高考班）评选逻辑。"""
    # Exclude students with no language score or no professional score
    valid_students = [
        r for r in students
        if _to_float(r["language_avg"]) > 0 and _to_float(r["professional_avg"]) > 0
    ]
    if not valid_students:
        return []

    # Grade language rank
    grade_lang_values = [(r["student_id"], r["language_avg"]) for r in valid_students]
    grade_lang_rank = _rank_desc(grade_lang_values)

    # Professional class rank
    class_groups: Dict[int, List[dict]] = {}
    for r in valid_students:
        class_groups.setdefault(r["class_id"], []).append(r)
    prof_class_rank: Dict[int, int] = {}
    for cls_rows in class_groups.values():
        vals = [(r["student_id"], r["professional_avg"]) for r in cls_rows]
        prof_class_rank.update(_rank_desc(vals))

    winners = []
    winner_ids = set()

    def add_winner(r, level):
        winners.append({
            "student_id": r["student_id"],
            "class_id": r["class_id"],
            "language_avg": round(_to_float(r["language_avg"]), 2),
            "professional_avg": round(_to_float(r["professional_avg"]), 2),
            "average_score": round(_to_float(r["language_avg"]) + _to_float(r["professional_avg"]), 2),
            "grade_rank": f"{grade_lang_rank.get(r['student_id'], 0)}/{len(grade_lang_values)}",
            "major_rank": f"{prof_class_rank.get(r['student_id'], 0)}/{len(class_groups.get(r['class_id'], []))}",
            "award_level": level,
        })
        winner_ids.add(r["student_id"])

    # Assign fixed prizes by language rank + professional class rank thresholds
    for r in sorted(valid_students, key=lambda x: grade_lang_rank.get(x["student_id"], 9999)):
        gr = grade_lang_rank.get(r["student_id"])
        pr = prof_class_rank.get(r["student_id"])
        if gr is None or pr is None:
            continue
        level = None
        if gr <= 3 and pr <= 10:
            level = "一等奖"
        elif 4 <= gr <= 6 and pr <= 15:
            level = "二等奖"
        elif 7 <= gr <= 9 and pr <= 20:
            level = "三等奖"
        if level and r["student_id"] not in winner_ids:
            add_winner(r, level)

    # 语数外年级第1名特评一等奖：即使专业班级排名未达前10，也给予一等奖
    if special_top_language_first_prize:
        top_lang_student = next(
            (r for r in valid_students if grade_lang_rank.get(r["student_id"]) == 1),
            None,
        )
        if top_lang_student and top_lang_student["student_id"] not in winner_ids:
            add_winner(top_lang_student, "一等奖")

    # 班级保底三等奖：某个班级没有学生获奖，则该班语数外+专业总分综合第一名特评三等奖
    for cls_id, cls_rows in class_groups.items():
        if any(w["class_id"] == cls_id for w in winners):
            continue
        top = max(cls_rows, key=lambda r: _to_float(r["language_avg"]) + _to_float(r["professional_avg"]))
        if top["student_id"] not in winner_ids:
            add_winner(top, "三等奖")

    return winners


def _screen_putong(students: List[dict]) -> List[Dict[str, Any]]:
    """普通升学班评选逻辑。"""
    # Exclude students with no language score or no professional score
    valid_students = [
        r for r in students
        if _to_float(r["language_avg"]) > 0 and _to_float(r["professional_avg"]) > 0
    ]
    if not valid_students:
        return []

    # Grade language rank (within this category)
    grade_lang_values = [(r["student_id"], r["language_avg"]) for r in valid_students]
    grade_lang_rank = _rank_desc(grade_lang_values)

    # Professional major rank within same grade + major
    major_groups: Dict[int, List[dict]] = {}
    for r in valid_students:
        major_groups.setdefault(r["major_id"], []).append(r)
    prof_major_rank: Dict[int, int] = {}
    for rows in major_groups.values():
        vals = [(r["student_id"], r["professional_avg"]) for r in rows]
        prof_major_rank.update(_rank_desc(vals))

    winners = []
    winner_ids = set()

    def add_winner(r, level):
        winners.append({
            "student_id": r["student_id"],
            "class_id": r["class_id"],
            "language_avg": round(_to_float(r["language_avg"]), 2),
            "professional_avg": round(_to_float(r["professional_avg"]), 2),
            "average_score": round(_to_float(r["language_avg"]) + _to_float(r["professional_avg"]), 2),
            "grade_rank": f"{grade_lang_rank.get(r['student_id'], 0)}/{len(grade_lang_values)}",
            "major_rank": f"{prof_major_rank.get(r['student_id'], 0)}/{len(major_groups.get(r['major_id'], []))}",
            "award_level": level,
        })
        winner_ids.add(r["student_id"])

    for r in sorted(valid_students, key=lambda x: grade_lang_rank.get(x["student_id"], 9999)):
        gr = grade_lang_rank.get(r["student_id"])
        pr = prof_major_rank.get(r["student_id"])
        if gr is None or pr is None:
            continue
        level = None
        if gr == 1 and pr <= 15:
            level = "一等奖"
        elif gr == 2 and pr <= 15:
            level = "二等奖"
        elif gr == 3 and pr <= 15:
            level = "三等奖"
        if level and r["student_id"] not in winner_ids:
            add_winner(r, level)

    return winners


def _screen_zhipu(students: List[dict]) -> List[Dict[str, Any]]:
    """职普融通班评选逻辑。

    方案：高一结束后够条件转入普高却选择留校的学生都享受一等奖学金。
    系统暂无转学资格数据，默认将该类别全部参评学生视为符合条件。
    如一等奖人数 >= 3，不再设置二、三等奖；如 < 3，按综合成绩补足 3 人名额。
    """
    valid_students = [r for r in students if _to_float(r["language_avg"]) > 0]
    if not valid_students:
        return []

    sorted_students = sorted(
        valid_students,
        key=lambda r: _to_float(r["language_avg"]) + _to_float(r["professional_avg"]),
        reverse=True,
    )

    winners = []
    for idx, r in enumerate(sorted_students):
        if len(sorted_students) >= 3:
            level = "一等奖"
        elif len(sorted_students) == 2:
            level = "一等奖" if idx == 0 else "二等奖"
        else:
            level = "一等奖"
        winners.append({
            "student_id": r["student_id"],
            "class_id": r["class_id"],
            "language_avg": round(_to_float(r["language_avg"]), 2),
            "professional_avg": round(_to_float(r["professional_avg"]), 2),
            "average_score": round(_to_float(r["language_avg"]) + _to_float(r["professional_avg"]), 2),
            "grade_rank": "-",
            "major_rank": "-",
            "award_level": level,
        })

    return winners


def run_screen(
    grade_id: int,
    class_type_ids: List[int],
    exam_ids: List[int],
    category: str,
    name: str = "",
    class_id: Optional[int] = None,
    options: Optional[dict] = None,
) -> int:
    if not exam_ids:
        raise ValueError("请至少选择一次考试")
    if not class_type_ids:
        raise ValueError("请至少选择一个班级类别")

    options = options or {}
    use_converted = options.get("use_converted_scores", False)
    special_top_language_first_prize = options.get("special_top_language_first_prize", True)

    category = category.strip()
    if category == "本科方向班":
        screen_fn = lambda students: _screen_benkefangxiang(students, special_top_language_first_prize)
    elif category in ("普通升学班", "普高升学班"):
        screen_fn = _screen_putong
    elif category == "职普融通班":
        screen_fn = _screen_zhipu
    else:
        raise ValueError(f"不支持的奖学金类别：{category}")

    with get_db() as conn:
        students = _fetch_student_averages(conn, grade_id, class_type_ids, exam_ids, use_converted)
        if not students:
            return 0

        winners = screen_fn(students)
        if not winners:
            return 0

        if class_id:
            winners = [w for w in winners if w["class_id"] == class_id]
            if not winners:
                return 0

        # ========== Phase 1 修复: 用 screen_run_id 隔离每次筛选 ==========
        now = datetime.now().isoformat(timespec='seconds')

        # 1. 创建 run 记录，拿到 run_id
        run_name = f"Grade{grade_id}_{category}_{now[:16]}"
        screen_run_id = _scholarship_repo.create_screen_run(
            run_name, grade_id, category, class_id,
            ",".join(str(e) for e in exam_ids), now, conn=conn)

        # 2. 按 run_id 清这次筛选留下的旧候选（同一 run 不应该有重复）
        _scholarship_repo.delete_by_run(screen_run_id, conn=conn)

        # 3. 插入候选，带上 screen_run_id（UNIQUE 索引在数据库层再兜一次）
        primary_exam_id = exam_ids[0]
        for w in winners:
            _scholarship_repo.upsert_candidate(
                w["student_id"], primary_exam_id, w["class_id"],
                w["average_score"], w["language_avg"], w["professional_avg"],
                total_score=w.get("total_score"),
                subjects_json=json.dumps(w.get("subjects", []), ensure_ascii=False),
                category=category,
                screen_run_id=screen_run_id,
                grade_rank=w["grade_rank"], major_rank=w["major_rank"],
                award_level=w["award_level"],
                review_status="待复核",
                conn=conn)
        conn.commit()
        return len(winners)
