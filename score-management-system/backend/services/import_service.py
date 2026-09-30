"""Import business logic — Service 层.

负责:
- 业务编排 (validate / confirm / confirm_batch)
- 调用 Repository 层 (import_file_repo, exam_repo, student_repo, ...)
- 复用 Router 层共享 helper (_load_records, _get_existing_class, ...)
- 不处理 HTTP — 异常直接抛出 (Router 负责转 HTTPException)
"""
import json
from typing import Optional, List, Dict
from pathlib import Path
import zipfile
import io

from database import get_db
from repositories.imports import ImportFileRepository, FileSubjectMappingRepository
from repositories.exams import ExamRepository, ExamSubjectConfigRepository
from repositories.students import StudentRepository
from repositories.classes import ClassRepository
from repositories.scores import ScoreRepository
from repositories.subject_standards import SubjectStandardRepository
from repositories.score_subject_details import ScoreSubjectDetailRepository
from repositories.stats import StatsRepository
from services.excel_parser import (
    parse_score_file, parse_score_file_with_meta,
    normalize_class_name, _extract_max_score_from_header,
)
from utils.common import now_str
from config import UPLOAD_DIR


# Repo 单例
import_file_repo = ImportFileRepository()
exam_repo = ExamRepository()
exam_cfg_repo = ExamSubjectConfigRepository()
student_repo = StudentRepository()
class_repo = ClassRepository()
score_repo = ScoreRepository()
subject_std_repo = SubjectStandardRepository()
score_detail_repo = ScoreSubjectDetailRepository()
stats_repo = StatsRepository()
mapping_repo = FileSubjectMappingRepository()


class ImportConflictError(Exception):
    """成绩冲突 — Router 负责转 HTTP 409."""
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__(f"发现 {len(conflicts)} 条成绩冲突，请人工确认后重试")


class UnknownClassError(Exception):
    """未知班级 — Router 负责转 HTTP 400."""
    def __init__(self, unknown_classes):
        self.unknown_classes = unknown_classes
        super().__init__(f"发现 {len(unknown_classes)} 个班级未在系统中设置，请调整班级名称或先创建班级")


# ===== Helper Functions =====

def _find_existing_exam(conn, name, exam_type, school_year=None, semester=None, month=None):
    return exam_repo.find_by_meta(name, exam_type, school_year, semester, month, conn=conn)


def _get_existing_class(conn, class_name):
    normalized = normalize_class_name(class_name, conn=conn)
    if not normalized:
        return None
    result = class_repo.get_by_name(normalized, conn=conn)
    if result:
        return result
    # 档案里括号全/半角不统一时，两种写法都试一次
    for variant in (normalized.replace("(", "（").replace(")", "）"),
                    normalized.replace("（", "(").replace("）", ")")):
        if variant != normalized:
            result = class_repo.get_by_name(variant, conn=conn)
            if result:
                return result
    if normalized.endswith("班（本方）"):
        result = class_repo.get_by_name(normalized[:-4], conn=conn)
        if result:
            return result
    if "（本方）" not in normalized:
        result = class_repo.get_by_name(normalized + "（本方）", conn=conn)
        if result:
            return result
    return None


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def _subject_total(records_dict):
    keys = ["语文", "数学", "英语", "专业课", "物理", "化学", "生物", "政治", "历史", "地理"]
    return sum(_num(records_dict.get(k)) or 0 for k in keys)


def _other_subject_total(records_dict):
    keys = ["物理", "化学", "生物", "政治", "历史", "地理"]
    return sum(_num(records_dict.get(k)) or 0 for k in keys)


def _get_or_create_student(conn, name, class_info, grade_id, major_id, student_no=None):
    class_id = class_info["id"]
    if student_no:
        sid = student_repo.get_by_student_no_and_class(student_no, class_id, conn=conn)
        if sid:
            return sid
    ids = student_repo.get_by_name_and_class(name, class_id, conn=conn)
    if ids:
        return ids[0]
    return student_repo.create_student(
        name, student_no, grade_id, major_id,
        class_info["class_type_id"], class_id, conn=conn)


def _resolve_student_id(conn, rec, class_info, exam_id=None):
    class_id = class_info["id"]
    student_no = str(rec.get("student_no") or "").strip()
    name = rec["name"].strip()
    if student_no:
        sid = student_repo.get_by_student_no_and_class(student_no, class_id, conn=conn)
        if sid:
            return sid
    ids = student_repo.get_by_name_and_class(name, class_id, conn=conn)
    if len(ids) == 1:
        return ids[0]
    if len(ids) > 1 and exam_id is not None:
        participated_ids = score_repo.check_students_participated(exam_id, ids, conn=conn)
        not_participated = [sid for sid in ids if sid not in participated_ids]
        if not_participated:
            return not_participated[0]
        return None
    if len(ids) > 1:
        return ids[0]
    return None


def _save_score_subject_details(conn, score_id, prof_scores, subject_config=None):
    if not prof_scores:
        return
    score_detail_repo.delete_by_score(score_id, conn=conn)
    for name, score in prof_scores.items():
        max_score = 100.0
        if subject_config and name in subject_config:
            try:
                max_score = float(subject_config[name].get("max_score", 100))
            except (ValueError, TypeError):
                pass
        score_detail_repo.insert_detail(score_id, name, score, max_score, conn=conn)


def _calc_professional_max_score(rec, subject_config=None):
    prof_scores = rec.get("professional_subject_scores") or {}
    if prof_scores:
        total = 0.0
        for name, score in prof_scores.items():
            if not name or not isinstance(name, str):
                continue
            norm = name.strip().lower()
            if norm.startswith("unnamed"):
                continue
            max_score = 100.0
            if subject_config and name in subject_config:
                try:
                    max_score = float(subject_config[name].get("max_score", 100))
                except (ValueError, TypeError):
                    pass
            else:
                extracted = _extract_max_score_from_header(name)
                if extracted is not None:
                    max_score = float(extracted)
            total += max_score
        return total if total > 0 else 100.0
    if subject_config and "专业课" in subject_config:
        try:
            return float(subject_config["专业课"].get("max_score", 100))
        except (ValueError, TypeError):
            pass
    return 100.0


def _import_records_into_exam(
    conn, records, exam_id, batch, grade_id, major_id,
    subject_config=None, class_mapping=None, overwrite_existing=False,
):
    class_mapping = class_mapping or {}
    inserted = 0
    updated = 0
    max_prof_max_score = 0.0
    conflicts = []
    unknown_classes = set()
    check_conflicts = not overwrite_existing

    subject_map = {
        "chinese_score": "语文", "math_score": "数学", "english_score": "英语",
        "physics_score": "物理", "chemistry_score": "化学", "biology_score": "生物",
        "history_score": "历史", "geography_score": "地理", "politics_score": "政治",
        "professional_score": "专业课",
    }

    for rec in records:
        if not rec["name"]:
            continue

        class_info = _get_existing_class(conn, rec.get("class_name", ""))
        if not class_info:
            mapped_class_id = class_mapping.get(rec.get("class_name", ""))
            if mapped_class_id:
                class_info = class_repo.get_by_id_detailed(mapped_class_id, conn=conn)
        if not class_info:
            raw_class = rec.get("class_name", "")
            if raw_class:
                unknown_classes.add(raw_class)
            continue

        sid = _resolve_student_id(conn, rec, class_info, exam_id=exam_id)
        if sid is None:
            sid = _get_or_create_student(
                conn, rec["name"], class_info,
                class_info["grade_id"], class_info["major_id"],
                student_no=str(rec.get("student_no") or "").strip())

        new_scores = {}
        for db_col, rec_key in subject_map.items():
            val = _num(rec.get(rec_key))
            if val is not None:
                new_scores[db_col] = val

        provided_total = _num(rec.get("总分"))
        prof_scores = rec.get("professional_subject_scores") or {}
        prof_max_score = _calc_professional_max_score(rec, subject_config)
        if prof_max_score > max_prof_max_score:
            max_prof_max_score = prof_max_score

        existing = score_repo.get_by_student_and_exam(sid, exam_id, conn=conn)

        if existing:
            if check_conflicts:
                conflict_fields = []
                for k, v in new_scores.items():
                    if v is not None and existing[k] is not None and existing[k] != "":
                        conflict_fields.append(subject_map.get(k, k))
                if conflict_fields:
                    conflicts.append({
                        "row_index": rec.get("row_index"),
                        "name": rec["name"],
                        "class_name": rec.get("class_name", ""),
                        "student_no": rec.get("student_no", ""),
                        "exam_id": exam_id,
                        "conflict_fields": conflict_fields,
                        "message": f"学生 {rec['name']} 在本次考试中已有 {','.join(conflict_fields)} 成绩，无法重复导入",
                    })
                    continue

            current = {
                "chinese_score": existing["chinese_score"],
                "math_score": existing["math_score"],
                "english_score": existing["english_score"],
                "physics_score": existing["physics_score"],
                "chemistry_score": existing["chemistry_score"],
                "biology_score": existing["biology_score"],
                "history_score": existing["history_score"],
                "geography_score": existing["geography_score"],
                "politics_score": existing["politics_score"],
                "professional_score": existing["professional_score"],
            }
            for k, v in new_scores.items():
                current[k] = v

            old_main_total = sum(
                v or 0 for v in [
                    existing["chinese_score"], existing["math_score"],
                    existing["english_score"], existing["professional_score"],
                    existing["physics_score"], existing["chemistry_score"],
                    existing["biology_score"], existing["history_score"],
                    existing["geography_score"], existing["politics_score"],
                ])
            existing_other = max(0, (existing["total_score"] or 0) - old_main_total)
            total = sum(v or 0 for v in current.values()) + existing_other + _other_subject_total(rec)

            if new_scores:
                fields = dict(new_scores)
                fields["total_score"] = total
                fields["professional_max_score"] = prof_max_score
                score_repo.update_scores(sid, exam_id, fields, conn=conn)
                updated += 1
            _save_score_subject_details(conn, existing["id"], prof_scores, subject_config)
        else:
            if provided_total is not None:
                total = provided_total
            else:
                total = _subject_total(rec)

            try:
                score_id = score_repo.insert_score(
                    sid, exam_id, new_scores, total, prof_max_score, batch, conn=conn)
                inserted += 1
                _save_score_subject_details(conn, score_id, prof_scores, subject_config)
            except Exception:
                conflicts.append({
                    "row_index": rec.get("row_index"),
                    "name": rec["name"],
                    "class_name": rec.get("class_name", ""),
                    "student_no": rec.get("student_no", ""),
                    "exam_id": exam_id,
                    "conflict_fields": list(subject_map.values()),
                    "message": f"学生 {rec['name']} 在本次考试中已存在成绩记录（并发冲突）",
                })

    if max_prof_max_score > 0:
        exam_cfg_repo.upsert(exam_id, "专业课", max_prof_max_score, conn=conn)

    if unknown_classes:
        raise UnknownClassError(sorted(unknown_classes))
    if conflicts:
        raise ImportConflictError(conflicts)

    return inserted, updated


def _update_statistics(conn):
    stats_repo.update_all_counts(conn=conn)


def _build_default_subject_config(major_id=None):
    config = {}
    rows = subject_std_repo.list_all_rows()
    for r in rows:
        if r["major_id"] is None:
            config.setdefault(r["subject_name"], {"max_score": r["max_score"]})
        elif r["major_id"] == major_id:
            config[r["subject_name"]] = {"max_score": r["max_score"]}
    for subj, default in [("语文", 150), ("数学", 150), ("英语", 100), ("专业课", 100)]:
        if subj not in config:
            config[subj] = {"max_score": default}
    return config


def _save_exam_subject_configs(conn, exam_id, subject_config=None, major_id=None):
    if not subject_config:
        subject_config = _build_default_subject_config(major_id)
    cleaned = {}
    for name, cfg in subject_config.items():
        if not name or not isinstance(name, str):
            continue
        max_score = cfg.get("max_score") if isinstance(cfg, dict) else cfg
        try:
            max_score = float(max_score)
        except (ValueError, TypeError):
            continue
        if max_score <= 0:
            continue
        cleaned[name] = max_score
    for name, max_score in cleaned.items():
        exam_cfg_repo.upsert(exam_id, name, max_score, conn=conn)


def _save_file_subject_mappings(conn, import_file_id, subject_config=None):
    if not subject_config:
        return
    mapping_repo.replace_all_for_file(import_file_id, subject_config, conn=conn)


def _build_exam_name_from_file(row) -> str:
    parts = [row["school_year"] or "", row["semester"] or ""]
    if row["exam_type"] == "月考" and row["month"]:
        parts.append(f"{row['month']}月")
    if row["exam_type"]:
        parts.append(row["exam_type"])
    return "".join(parts) or "导入考试"


# ===== Load Records (shared with Router) =====

def _find_saved_file_legacy(row):
    prefix = f"{row['created_at'].replace(':', '').replace('-', '').replace(' ', '')}_"
    for p in UPLOAD_DIR.iterdir():
        if p.name.endswith(row["file_name"]) and p.name.startswith(prefix[:14]):
            return str(p)
    return None


def load_records(file_row):
    saved_path = file_row["file_path"] or _find_saved_file_legacy(file_row)
    if not saved_path or not Path(saved_path).exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="服务器文件已丢失")
    content = Path(saved_path).read_bytes()
    filename = file_row["file_name"]
    if filename.lower().endswith(".zip"):
        records = []
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                records.extend(parse_score_file(zf.read(ef), ef))
        return records
    return parse_score_file(content, filename)


def load_records_with_meta(file_row):
    saved_path = file_row["file_path"] or _find_saved_file_legacy(file_row)
    if not saved_path or not Path(saved_path).exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="服务器文件已丢失")
    content = Path(saved_path).read_bytes()
    filename = file_row["file_name"]
    if filename.lower().endswith(".zip"):
        records = []
        detected_subjects = []
        professional_subjects = []
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                meta = parse_score_file_with_meta(zf.read(ef), ef)
                records.extend(meta["records"])
                detected_subjects.extend(meta.get("detected_subjects", []))
                professional_subjects.extend(meta.get("professional_subjects", []))
        detected_map = {item["name"]: item for item in detected_subjects}
        prof_map = {item["name"]: item for item in professional_subjects}
        return {
            "records": records,
            "detected_subjects": list(detected_map.values()),
            "professional_subjects": list(prof_map.values()),
        }
    return parse_score_file_with_meta(content, filename)


# ===== Service API (called by Router) =====

def validate_import_file(file_id: int):
    """Validate an import file — 返回校验结果 dict."""
    from fastapi import HTTPException
    row = import_file_repo.get_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")

    meta = load_records_with_meta(row)
    records = meta["records"]

    errors, warnings = [], []
    duplicate_count = 0
    missing_count = 0
    unknown_classes = set()

    with get_db() as conn:
        seen = set()
        for rec in records:
            if not rec["name"]:
                errors.append({"row": rec["row_index"], "msg": "姓名缺失", "sheet": rec.get("sheet_name", "")})
                missing_count += 1
                continue
            key = (rec["name"], rec.get("class_name", ""))
            if key in seen:
                warnings.append({"row": rec["row_index"], "msg": f"重复学生 '{rec['name']}'", "sheet": rec.get("sheet_name", "")})
                duplicate_count += 1
            seen.add(key)
            class_name = rec.get("class_name", "")
            if class_name:
                class_info = _get_existing_class(conn, class_name)
                if not class_info:
                    unknown_classes.add(class_name)

    if unknown_classes:
        sorted_unknown = sorted(unknown_classes)
        errors.append({"row": 0, "msg": f"以下班级未在系统中设置，请调整或先创建班级：{', '.join(sorted_unknown)}",
                       "sheet": "", "unknown_classes": sorted_unknown})
    if not records:
        errors.append({"row": 0, "msg": "未解析到任何成绩记录", "sheet": ""})

    status = "校验失败" if errors else "校验通过"
    import_file_repo.update_validation(file_id, status, duplicate_count, missing_count)

    user_config = {}
    if row["subject_config"]:
        try:
            user_config = json.loads(row["subject_config"])
        except Exception:
            pass

    detected_subjects = meta.get("detected_subjects", [])
    professional_subjects = meta.get("professional_subjects", [])
    for item in detected_subjects + professional_subjects:
        name = item["name"]
        if name in user_config:
            try:
                item["max_score"] = float(user_config[name].get("max_score", item["max_score"]))
            except (ValueError, AttributeError):
                pass

    return {
        "status": status, "records": len(records),
        "errors": errors[:50], "warnings": warnings[:50],
        "duplicate_count": duplicate_count, "missing_count": missing_count,
        "unknown_classes": sorted(unknown_classes),
        "detected_subjects": detected_subjects,
        "professional_subjects": professional_subjects,
    }


def confirm_import_file(file_id: int, payload):
    """Confirm single file import — 返回 {exam_id, inserted, updated, merged}."""
    from fastapi import HTTPException
    from utils.logger import log_operation

    row = import_file_repo.get_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")

    records = load_records(row)
    if not records:
        raise HTTPException(status_code=400, detail="文件中未解析到成绩记录")

    with get_db() as conn:
        grade_id = row["grade_id"]
        major_id = row["major_id"]
        school_year = payload.school_year or row["school_year"]
        semester = payload.semester or row["semester"]
        month = payload.month if payload.month is not None else row["month"]

        if payload.merge_exam_id:
            exam = exam_repo.get_by_id(payload.merge_exam_id)
            if not exam:
                raise HTTPException(status_code=404, detail="要合并的考试不存在")
            exam_id = exam["id"]
            is_merge = True
        else:
            existing_id = _find_existing_exam(conn, payload.exam_name, row["exam_type"], school_year, semester, month)
            if existing_id:
                exam_id = existing_id
                is_merge = True
            else:
                exam_id = exam_repo.create_exam(
                    payload.exam_name, row["exam_type"], school_year, semester, month,
                    payload.exam_date or now_str()[:10], conn=conn)
                is_merge = False

        _save_exam_subject_configs(conn, exam_id, payload.subject_config, major_id)
        _save_file_subject_mappings(conn, file_id, payload.subject_config)

        batch = f"{payload.exam_name}_{exam_id}"
        try:
            inserted, updated = _import_records_into_exam(
                conn, records, exam_id, batch, grade_id, major_id,
                subject_config=payload.subject_config,
                class_mapping=payload.class_mapping,
                overwrite_existing=payload.overwrite_existing or False,
            )
        except UnknownClassError as e:
            raise HTTPException(status_code=400,
                detail={"message": str(e), "unknown_classes": e.unknown_classes, "code": "UNKNOWN_CLASS"})
        except ImportConflictError as e:
            raise HTTPException(status_code=409,
                detail={"message": str(e), "conflicts": e.conflicts, "code": "IMPORT_CONFLICT"})

        _update_statistics(conn)
        import_file_repo.mark_imported(file_id)
        if not is_merge:
            exam_repo.mark_imported(exam_id, conn=conn)
        log_operation("数据导入", f"确认导入 {payload.exam_name}，新增 {inserted} 条，更新 {updated} 条")

        return {"exam_id": exam_id, "inserted": inserted, "updated": updated, "merged": is_merge}


def confirm_batch_import_files(payload):
    """Confirm batch import — 返回 results list."""
    from fastapi import HTTPException
    from utils.logger import log_operation

    if not payload.files:
        raise HTTPException(status_code=400, detail="未选择要导入的文件")

    file_ids = [f.file_id for f in payload.files]
    file_name_map = {f.file_id: f.exam_name for f in payload.files}
    file_config_map = {
        f.file_id: {"class_mapping": f.class_mapping, "overwrite_existing": f.overwrite_existing or False}
        for f in payload.files
    }

    rows = import_file_repo.get_by_ids(file_ids)
    if len(rows) != len(file_ids):
        raise HTTPException(status_code=404, detail="部分文件不存在")

    not_ready = [
        r["file_name"] for r in rows
        if r["validation_status"] != "校验通过" and not file_config_map.get(r["id"], {}).get("overwrite_existing", False)
    ]
    if not_ready:
        raise HTTPException(status_code=400, detail=f"以下文件未校验通过：{', '.join(not_ready)}")

    results = []
    total_inserted = total_updated = 0

    for row in rows:
        records = load_records(row)
        if not records:
            results.append({"file_id": row["id"], "file_name": row["file_name"],
                            "exam_id": None, "exam_name": None,
                            "inserted": 0, "updated": 0, "skipped": True, "reason": "未解析到成绩记录"})
            continue

        exam_name = file_name_map.get(row["id"]) or _build_exam_name_from_file(row)
        grade_id = row["grade_id"]
        major_id = row["major_id"]
        school_year = row["school_year"]
        semester = row["semester"]
        month = row["month"]
        exam_type = row["exam_type"]

        with get_db() as conn:
            existing_id = _find_existing_exam(conn, exam_name, exam_type, school_year, semester, month)
            if existing_id:
                exam_id = existing_id
                is_merge = True
            else:
                exam_id = exam_repo.create_exam(
                    exam_name, exam_type, school_year, semester, month,
                    payload.exam_date or now_str()[:10], conn=conn)
                is_merge = False

            _save_exam_subject_configs(conn, exam_id, payload.subject_config, major_id)
            _save_file_subject_mappings(conn, row["id"], payload.subject_config)

            file_config = file_config_map.get(row["id"]) or {}
            batch = f"{exam_name}_{exam_id}"
            try:
                inserted, updated = _import_records_into_exam(
                    conn, records, exam_id, batch, grade_id, major_id,
                    subject_config=payload.subject_config,
                    class_mapping=file_config.get("class_mapping"),
                    overwrite_existing=file_config.get("overwrite_existing", False),
                )
            except UnknownClassError as e:
                conn.rollback()
                results.append({"file_id": row["id"], "file_name": row["file_name"],
                                "exam_id": None, "exam_name": exam_name,
                                "inserted": 0, "updated": 0, "skipped": True, "reason": str(e),
                                "unknown_classes": e.unknown_classes})
                continue
            except ImportConflictError as e:
                conn.rollback()
                results.append({"file_id": row["id"], "file_name": row["file_name"],
                                "exam_id": None, "exam_name": exam_name,
                                "inserted": 0, "updated": 0, "skipped": True, "reason": str(e),
                                "conflicts": e.conflicts})
                continue

            total_inserted += inserted
            total_updated += updated
            _update_statistics(conn)
            import_file_repo.mark_imported(row["id"])
            if not is_merge:
                exam_repo.mark_imported(exam_id, conn=conn)
            log_operation("数据导入", f"确认导入 {exam_name}，新增 {inserted} 条，更新 {updated} 条")

        results.append({"file_id": row["id"], "file_name": row["file_name"],
                        "exam_id": exam_id, "exam_name": exam_name,
                        "inserted": inserted, "updated": updated, "merged": is_merge})

    log_operation("数据导入", f"批量确认导入 {len(results)} 个文件，新增 {total_inserted} 条，更新 {total_updated} 条")
    return {"results": results, "total_inserted": total_inserted,
            "total_updated": total_updated, "file_count": len(results)}
