"""Score conversion logic."""
from typing import Optional

from database import get_db


def get_subject_standards():
    with get_db() as conn:
        rows = conn.execute("SELECT subject_name, major_id, max_score, pass_score FROM subject_standards").fetchall()
    fixed = {}
    by_major = {}
    for r in rows:
        if r["major_id"] is None:
            fixed[r["subject_name"]] = {"max": r["max_score"], "pass": r["pass_score"]}
        else:
            by_major.setdefault(r["major_id"], {})[r["subject_name"]] = {"max": r["max_score"], "pass": r["pass_score"]}
    return fixed, by_major


def get_exam_subject_configs(exam_id: int) -> dict:
    """Return subject_name -> max_score mapping for an exam."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT subject_name, max_score FROM exam_subject_configs WHERE exam_id=?",
            (exam_id,),
        ).fetchall()
    return {r["subject_name"]: r["max_score"] for r in rows}


def convert_score(original: float, original_max: float, target_max: float) -> float:
    if original is None or original_max is None or target_max is None or original_max == 0:
        return None
    return round(original * target_max / original_max, 2)


def _convert_professional_details(conn, score_id: int, prof_target_max: float) -> Optional[float]:
    """Convert each professional subject detail score and return the sum.

    Each detail is converted proportionally so that the sum of converted
    detail scores equals the converted professional total. This implements
    the "convert details first, then summarize" requirement.
    """
    detail_rows = conn.execute(
        "SELECT id, original_score, max_score FROM score_subject_details WHERE score_id=?",
        (score_id,),
    ).fetchall()
    if not detail_rows:
        return None

    # Use the sum of detail full marks as the original professional total max.
    original_max = sum(float(d["max_score"] or 100) for d in detail_rows)
    if original_max == 0:
        return None

    ratio = prof_target_max / original_max
    converted_total = 0.0
    for d in detail_rows:
        original = d["original_score"]
        converted = round(original * ratio, 2) if original is not None else None
        conn.execute(
            "UPDATE score_subject_details SET converted_score=? WHERE id=?",
            (converted, d["id"]),
        )
        if converted is not None:
            converted_total += converted

    return round(converted_total, 2)


def convert_scores(exam_id: int, score_ids: list = None, target_max_map: dict = None):
    """Convert raw scores to standard scores for an exam.

    target_max_map example: {"语文": 150, "数学": 150, "英语": 100, "专业课": 100}
    If None, use system standards.

    For professional courses, individual subject details are converted first
    and then summed, so that converted detail scores add up to the converted
    professional total.
    """
    fixed, by_major = get_subject_standards()
    base_target = target_max_map or {
        "语文": fixed.get("语文", {}).get("max", 150),
        "数学": fixed.get("数学", {}).get("max", 150),
        "英语": fixed.get("英语", {}).get("max", 100),
        "专业课": 100,
    }
    exam_cfg = get_exam_subject_configs(exam_id)

    with get_db() as conn:
        where = "WHERE s.exam_id=?"
        params = [exam_id]
        if score_ids:
            placeholders = ",".join(["?"] * len(score_ids))
            where += f" AND s.id IN ({placeholders})"
            params.extend(score_ids)

        rows = conn.execute(
            f"SELECT s.*, st.major_id FROM scores s JOIN students st ON s.student_id=st.id {where}",
            params,
        ).fetchall()

        updated = 0
        for r in rows:
            major_id = r["major_id"]
            prof_max = by_major.get(major_id, {}).get("专业课", {}).get("max", 100)
            target = dict(base_target)
            target["专业课"] = prof_max

            chinese_c = convert_score(r["chinese_score"], exam_cfg.get("语文", 150), target["语文"])
            math_c = convert_score(r["math_score"], exam_cfg.get("数学", 150), target["数学"])
            english_c = convert_score(r["english_score"], exam_cfg.get("英语", 100), target["英语"])

            # Convert professional details first if available; otherwise fall back to total.
            prof_c = _convert_professional_details(conn, r["id"], prof_max)
            if prof_c is None:
                prof_c = convert_score(
                    r["professional_score"],
                    exam_cfg.get("专业课", r["professional_max_score"] or 100),
                    prof_max,
                )

            converted_total = sum([v for v in [chinese_c, math_c, english_c, prof_c] if v is not None])

            conn.execute(
                """UPDATE scores SET
                chinese_converted=?, math_converted=?, english_converted=?, professional_converted=?,
                professional_max_score=?, total_converted=?, is_converted=?
                WHERE id=?""",
                (chinese_c, math_c, english_c, prof_c, prof_max, converted_total, 1, r["id"]),
            )
            updated += 1

        conn.commit()
    return updated
