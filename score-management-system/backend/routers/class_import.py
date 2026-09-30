"""班级名单导入路由 — 上传班级名单文件，批量校验/补齐班级档案.

预览接口只解析不写库；确认接口逐条创建班级（创建前再次校验，避免并发/重复）。
"""
import os
import re
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from repositories.classes import ClassRepository
from repositories.grades import GradeRepository
from repositories.majors import MajorRepository
from repositories.class_types import ClassTypeRepository
from services.course_file_parser import (
    _grids_xlsx,
    _grids_xls,
    _grids_docx,
    _grids_pdf,
)
from services.excel_parser import normalize_class_name
from utils.logger import log_operation

router = APIRouter()

class_repo = ClassRepository()
grade_repo = GradeRepository()
major_repo = MajorRepository()
ct_repo = ClassTypeRepository()

CLASS_FILE_EXTS = (".xlsx", ".xlsm", ".xls", ".docx", ".pdf")

# 表头别名：班级名列至少要能识别到，年级/专业/班级类别缺失时不做推断，交人工确认
_HEADER_ALIASES = {
    "class_name": ("班级名称", "班级", "名称", "行政班", "班别"),
    "grade": ("年级名称", "年级"),
    "major": ("专业名称", "专业"),
    "class_type": ("班级类别", "班级类型", "班型", "类别"),
}
# 精确匹配优先；子串匹配时「班级类别」需先于「班级」判断
_EXACT_ORDER = ("class_name", "grade", "major", "class_type")
_SUBSTRING_ORDER = ("class_type", "grade", "major", "class_name")
MAX_HEADER_SCAN = 10


# ============ 解析 ============

def _norm_cell(value):
    return "" if value is None else str(value).strip()


def _match_header(text):
    t = re.sub(r"\s+", "", _norm_cell(text))
    if not t or len(t) > 12:
        return None
    for key in _EXACT_ORDER:
        if t in _HEADER_ALIASES[key]:
            return key
    for key in _SUBSTRING_ORDER:
        for name in _HEADER_ALIASES[key]:
            if name in t:
                return key
    return None


def _locate_header(grid):
    for i in range(min(len(grid), MAX_HEADER_SCAN)):
        mapping = {}
        for j, cell in enumerate(grid[i]):
            key = _match_header(cell)
            if key and key not in mapping:
                mapping[key] = j
        if "class_name" in mapping:
            return i, mapping
    return -1, {}


def _rows_from_grid(grid, sheet):
    if not grid:
        return []
    header_row, cols = _locate_header(grid)
    if header_row < 0:
        return []
    out = []
    for row in grid[header_row + 1:]:
        def cell(key):
            j = cols.get(key)
            if j is None or j >= len(row):
                return ""
            return _norm_cell(row[j])

        name = cell("class_name")
        if not name:
            continue
        out.append({
            "name": name,
            "grade": cell("grade"),
            "major": cell("major"),
            "class_type": cell("class_type"),
            "sheet": sheet,
        })
    return out


def _grids(filename, data):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return _grids_xlsx(data)
    if ext == ".xls":
        return _grids_xls(data)
    if ext == ".docx":
        return _grids_docx(data)
    if ext == ".pdf":
        return _grids_pdf(data)
    raise ValueError("不支持的文件格式 %s（仅支持 Excel / Word / PDF）" % (ext or "未知"))


def parse_class_file(filename, data):
    """解析班级名单文件，返回 [{name, grade, major, class_type, sheet}]。"""
    rows = []
    for sheet, grid in _grids(filename, data):
        rows.extend(_rows_from_grid(grid, sheet))
    return rows


# ============ 名称规范化 ============

def _norm_text(value):
    return (_norm_cell(value)
            .replace("（", "(").replace("）", ")")
            .replace(" ", "").replace("\u3000", ""))


def _norm_grade(value):
    """年级归一：2026级 / 26级 / 2026 视为同一。"""
    t = re.sub(r"\s+", "", _norm_cell(value))
    m = re.search(r"(\d+)", t)
    if not m:
        return _norm_text(t)
    d = m.group(1)
    if len(d) == 2:
        d = "20" + d
    return d


def _grade_index():
    idx = {}
    for r in grade_repo.get_all():
        idx[_norm_grade(r["name"])] = (r["id"], r["name"])
    return idx


def _text_index(repo):
    idx = {}
    for r in repo.get_all():
        idx[_norm_text(r["name"])] = (r["id"], r["name"])
    return idx


def _class_keys(name):
    """一个班级名对应的多种比对键：原值 / 去括号差异 / normalize 结果。"""
    keys = {name.strip(), _norm_text(name)}
    try:
        keys.add(normalize_class_name(name))
    except Exception:
        pass
    return keys


def _class_exist_keys():
    keys = set()
    for _id, name in class_repo.list_basic():
        keys |= _class_keys(name or "")
    return keys


# ============ 接口 ============

@router.post("/class-import/preview")
async def preview_class_import(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件内容为空")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in CLASS_FILE_EXTS:
        raise HTTPException(400, "不支持的文件格式，仅支持 Excel / Word / PDF")
    try:
        rows = parse_class_file(file.filename, content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, "解析失败: %s" % e)
    if not rows:
        raise HTTPException(400, "未识别到班级名单，请确认文件含「班级名称」列")

    grade_idx = _grade_index()
    major_idx = _text_index(major_repo)
    ct_idx = _text_index(ct_repo)
    exist_keys = _class_exist_keys()

    to_create, exists, unrecognized, duplicates = [], [], [], []
    seen, dup_seen = set(), set()

    for r in rows:
        raw = r["name"].strip()
        try:
            file_key = normalize_class_name(raw) or _norm_text(raw)
        except Exception:
            file_key = _norm_text(raw)
        if file_key in seen:
            if raw not in dup_seen:
                dup_seen.add(raw)
                duplicates.append(raw)
            continue
        seen.add(file_key)

        reasons = []
        g = grade_idx.get(_norm_grade(r["grade"])) if r["grade"] else None
        if not r["grade"]:
            reasons.append("缺少年级信息")
        elif not g:
            reasons.append("年级未在档案中找到：%s" % r["grade"])
        m = major_idx.get(_norm_text(r["major"])) if r["major"] else None
        if not r["major"]:
            reasons.append("缺少专业信息")
        elif not m:
            reasons.append("专业未在档案中找到：%s" % r["major"])
        ct = ct_idx.get(_norm_text(r["class_type"])) if r["class_type"] else None
        if not r["class_type"]:
            reasons.append("缺少班级类别信息")
        elif not ct:
            reasons.append("班级类别未在档案中找到：%s" % r["class_type"])

        if reasons:
            unrecognized.append({"name": raw, "reason": "；".join(reasons)})
            continue

        if _class_keys(raw) & exist_keys:
            exists.append({"name": raw, "grade_name": g[1], "major_name": m[1]})
            continue

        to_create.append({
            "name": raw,
            "grade_id": g[0], "grade_name": g[1],
            "major_id": m[0], "major_name": m[1],
            "class_type_id": ct[0], "class_type_name": ct[1],
        })

    return {
        "file_name": file.filename,
        "total": len(rows),
        "to_create": to_create,
        "exists": exists,
        "duplicate_in_file": duplicates,
        "unrecognized": unrecognized,
    }


class ConfirmRow(BaseModel):
    name: str
    grade_id: int
    major_id: int
    class_type_id: int


class ConfirmClassImport(BaseModel):
    rows: List[ConfirmRow] = []


@router.post("/class-import/confirm")
def confirm_class_import(payload: ConfirmClassImport):
    valid_grades = {r["id"] for r in grade_repo.get_all()}
    valid_majors = {r["id"] for r in major_repo.get_all()}
    valid_cts = {r["id"] for r in ct_repo.get_all()}
    exist_keys = _class_exist_keys()

    created = 0
    skipped = []
    for row in payload.rows:
        name = (row.name or "").strip()
        if not name:
            skipped.append({"name": row.name, "reason": "班级名称为空"})
            continue
        if row.grade_id not in valid_grades:
            skipped.append({"name": name, "reason": "年级不存在"})
            continue
        if row.major_id not in valid_majors:
            skipped.append({"name": name, "reason": "专业不存在"})
            continue
        if row.class_type_id not in valid_cts:
            skipped.append({"name": name, "reason": "班级类别不存在"})
            continue
        if _class_keys(name) & exist_keys:
            skipped.append({"name": name, "reason": "已存在"})
            continue
        try:
            class_repo.create(name, row.grade_id, row.major_id, row.class_type_id)
        except Exception as e:
            skipped.append({"name": name, "reason": "创建失败：%s" % e})
            continue
        created += 1
        exist_keys |= _class_keys(name)

    log_operation("班级名单导入", "新建 %d 个班级, 跳过 %d 个" % (created, len(skipped)))
    return {"created": created, "skipped": skipped}
