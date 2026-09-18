"""Enhanced Excel parser for score import.

Supports multi-engine reading, multi-sheet parsing, multi-level headers,
and intelligent column mapping for various score sheet formats.
"""
import io
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import pandas as pd

from repositories.class_name_standards import ClassNameStandardsRepository
from repositories.class_name_aliases import ClassNameAliasesRepository

_cn_standards_repo = ClassNameStandardsRepository()
_cn_aliases_repo = ClassNameAliasesRepository()


STUDENT_ID_KEYWORDS = ["学号", "准考证号", "考号", "学籍号", "考生号", "报名号"]

SUBJECT_KEYWORDS = {
    "chinese": ["语文"],
    "math": ["数学"],
    "english": ["英语"],
    "physics": ["物理"],
    "chemistry": ["化学"],
    "biology": ["生物"],
    "politics": ["政治", "思想政治", "道法", "道德与法治"],
    "history": ["历史"],
    "geography": ["地理"],
    "professional": [
        "专业", "信息技术", "办公应用", "网络应用", "电子电工", "电子元器件",
        "汽车文化", "汽车构造", "汽车机械", "机械制图", "金属加工", "数控",
        "旅游地理", "旅游概论", "餐饮服务", "前厅", "幼儿保育", "心理", "卫生",
        "单片机", "电工", "机械基础", "教育类", "计算机类", "电子信息类",
        "加工制造类", "财经商贸类", "交通运输类", "旅游服务类", "餐饮类",
        "土木水利类", "医药卫生类", "汽车类", "智能制造", "保教政策",
        # 兼容部分成绩表省略“类”字的列名
        "电子信息", "计算机", "汽车", "旅游", "机械", "数控",
    ],
    "total": ["总分", "总得分", "总成绩"],
}

# Human-readable subject keys used in output records.
SUBJECT_LABELS = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "politics": "政治",
    "history": "历史",
    "geography": "地理",
    "professional": "专业课",
    "total": "总分",
}

# Columns that should never be treated as subject scores.
EXCLUDE_HEADER_KEYWORDS = [
    "排名", "名次", "主观分", "客观分", "主观", "客观",
    "班级排名", "年级排名", "班排名", "级排名",
]


def _read_with_engines(path_or_bytes, sheet_name=None, header=None, engine=None, **kwargs):
    """Try multiple engines to read an Excel file."""
    if engine:
        engines = [engine]
    else:
        engines = [None, "openpyxl", "calamine", "xlrd"]
    last_err = None
    for eng in engines:
        try:
            if eng:
                return pd.read_excel(path_or_bytes, sheet_name=sheet_name, header=header, engine=eng, **kwargs)
            return pd.read_excel(path_or_bytes, sheet_name=sheet_name, header=header, **kwargs)
        except Exception as e:
            last_err = e
            continue
    raise last_err or ValueError("无法读取 Excel 文件")


def _list_sheets(path_or_bytes) -> Tuple[List[str], Optional[str]]:
    """List sheet names with multiple engines."""
    engines = [None, "openpyxl", "calamine", "xlrd"]
    last_err = None
    for engine in engines:
        try:
            xl = pd.ExcelFile(path_or_bytes, engine=engine)
            return xl.sheet_names, engine
        except Exception as e:
            last_err = e
            continue
    raise last_err or ValueError("无法读取 Excel 文件")


def _find_detail_header_row(df: pd.DataFrame) -> Optional[int]:
    """Find the row containing detailed headers like name/score columns.

    To avoid matching category rows (e.g. 考生信息/总成绩/语文/数学/英语),
    require the row to contain both a student-info marker and a score marker.
    """
    student_markers = ["姓名", "准考证号", "考号", "班级名称", "班级"]
    score_markers = ["语文", "数学", "英语", "原始分", "总得分", "总分", "专业"]
    for idx, row in df.iterrows():
        row_text = " ".join(str(x) for x in row if pd.notna(x))
        has_student = any(m in row_text for m in student_markers)
        has_score = any(m in row_text for m in score_markers)
        if has_student and has_score:
            return idx
    return None


def _is_category_row(row: pd.Series) -> bool:
    """Check if a row is a category header row (e.g. 考生信息/总成绩/语文/数学/英语)."""
    row_text = " ".join(str(x) for x in row if pd.notna(x))
    categories = ["考生信息", "总成绩", "语文", "数学", "英语", "专业"]
    return sum(1 for c in categories if c in row_text) >= 2


def _clean_value(v: Any) -> Any:
    """Clean score values: convert to float, handle special values."""
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ["--", "缺考", "-", "", "None", "/", "\\", "—"]:
        return None
    try:
        return float(s)
    except ValueError:
        return s


def _normalize_header(h: Any) -> str:
    """Normalize header text for matching."""
    if pd.isna(h):
        return ""
    return re.sub(r"\s+", "", str(h))


def _extract_max_score_from_header(h: Any) -> Optional[float]:
    """从列名中提取满分，如 '电子元器件检测与识别（100分）' -> 100.0。"""
    if pd.isna(h):
        return None
    s = str(h).strip()
    # 匹配 （100分）、(100分)、100分
    m = re.search(r"[（(](\d+(?:\.\d+)?)\s*分?[）)]", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*分$", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _header_contains_any(h: str, keywords: List[str]) -> bool:
    """Check whether normalized header contains any of the keywords."""
    h = _normalize_header(h)
    return any(k in h for k in keywords)


def _header_excluded(h: str) -> bool:
    """Check whether a header should be excluded (rank, objective/subjective, etc.)."""
    return _header_contains_any(h, EXCLUDE_HEADER_KEYWORDS)


def _match_column(headers: List[str], keywords: List[str], exclude: Optional[List[str]] = None) -> Optional[int]:
    """Find column index matching keywords."""
    matches = _match_columns(headers, keywords, exclude)
    return matches[0] if matches else None


def _match_columns(headers: List[str], keywords: List[str], exclude: Optional[List[str]] = None) -> List[int]:
    """Find all column indices matching keywords."""
    exclude = exclude or []
    result = []
    for i, h in enumerate(headers):
        h = _normalize_header(h)
        if any(k in h for k in exclude):
            continue
        if any(k in h for k in keywords):
            result.append(i)
    return result


# 本地硬编码别名兜底（仅在数据库未命中时使用）
_CLASS_NAME_ALIASES_LOCAL = {
    "25级数控本方班": "25级数控2班（本方）",
    "25级旅游本方班": "25级旅游2班（本方）",
    "25级电子本方班": "25级电子5班（本方）",
    "25级计算机本方班": "25级计算机3班（本方）",
    "25级保育本方班": "25级保育2班（本方）",
}


def normalize_class_name(name: str, conn=None) -> str:
    """Normalize class name for deduplication.

    三级规范化策略：
    1. 查询 class_name_aliases 别名映射表
    2. 查询 class_name_standards 标准名称库
    3. 本地正则兜底规范化
    """
    if not name:
        return name
    s = str(name).strip()
    s = s.replace("（", "(").replace("）", ")")
    
    # 第1级：数据库别名映射表
    canonical = _cn_aliases_repo.find_canonical(s, conn=conn)
    if canonical:
            return row["canonical_name"]
    
    # 第2级：规范名称库确认
    std_name = _cn_standards_repo.find_by_name(s, conn=conn)
    if std_name:
            return row["name"]
    
    # 第3级：本地硬编码别名兜底
    s = _CLASS_NAME_ALIASES_LOCAL.get(s, s)
    
    # 第4级：正则规范化
    normalized = _regex_normalize_class_name(s)

    # 第5级：正则结果再次匹配规范名称库
    if normalized != s:
        std_name2 = _cn_standards_repo.find_by_name(normalized, conn=conn)
        if std_name2:
            return row["name"]

    return normalized


def _regex_normalize_class_name(s: str) -> str:
    """兜底正则规范化，处理常见缩写、后缀。"""
    # 国防特色班级名称必须保持原样，不做任何修改
    if re.search(r"国防特色", s):
        return s

    # Detect "本方" suffix before stripping; re-attach at the end in unified format.
    has_benfang = bool(re.search(r"\(本方\)", s) or s.endswith("本方班"))

    # Remove other common suffixes that don't change class identity
    s = re.sub(r"(半期|期末|期中|月考|成绩|记分册|登记表)$", "", s).strip()
    # Ensure grade suffix "级" is present and uniform, but do not add it to bare class numbers like "01班".
    s = re.sub(r"^(\d{2})(?!级)(?!班)", r"\1级", s)
    s = re.sub(r"^(20\d{2})(?!级)(?!班)", r"\1级", s)

    # Expand single-character major abbreviations: 计->计算机, 电->电子, 数->数控
    def _expand_major_abbr(match):
        grade = match.group(1)
        abbr = match.group(2)
        rest = match.group(3)
        mapping = {"计": "计算机", "电": "电子", "数": "数控"}
        return f"{grade}{mapping.get(abbr, abbr)}{rest}"

    s = re.sub(r"^(\d{2,4}级)\s*(计|电|数)\s*(\d+班?)$", _expand_major_abbr, s)

    # For numbered majors, default missing class number to 1 (e.g. 24级计算机班 -> 24级计算机1班)
    numbered_majors = ["计算机", "电子", "数控", "汽修", "汽车", "旅游", "保育", "机械"]
    numbered_major_re = "|".join(numbered_majors)
    s = re.sub(rf"^(\d{{2,4}}级)({numbered_major_re})班(\(本方\))?$", r"\g<1>\g<2>1班\g<3>", s)

    # Expand "运动" / "运动训练" class names to uniform "运动训练班"
    s = re.sub(r"^(\d{2,4}级)运动(训练)?班?$", lambda m: f"{m.group(1)}运动训练班", s)

    # Remove trailing branch suffixes: -A班, -A, (A班)
    s = re.sub(r"[-\-\－]\s*[A-Za-z]\s*班?$", "", s).strip()
    s = re.sub(r"[（(]\s*[A-Za-z]\s*班?\s*[）)]$", "", s).strip()

    # Strip any existing "本方" suffix variants so we can re-attach a unified one.
    s = re.sub(r"\s*\(本方\)\s*班\s*$", "", s).strip()
    s = re.sub(r"\s*\(本方\)\s*$", "", s).strip()
    s = re.sub(r"\s*本方班\s*$", "", s).strip()

    # Ensure class name ends with "班"
    if s and not s.endswith("班"):
        s += "班"

    # Re-attach "本方" suffix in unified full-width format
    if has_benfang:
        s = re.sub(r"\s*班\s*$", "", s).strip()
        s += "班（本方）"

    return s


def _extract_grade_from_filename(filename: str) -> str:
    """Extract grade prefix like '24级' from filename.

    Supports both clean filenames and uploaded filenames prefixed with file_id,
    e.g. '24级10月月考成绩.xlsx' -> '24级' and '76_24级10月月考成绩.xlsx' -> '24级'.
    """
    base = Path(filename).stem
    m = re.search(r"(?:^|_)(\d{2,4})级", base)
    return m.group(1) + "级" if m else ""


def _class_name_from_sheet(sheet_name: str) -> str:
    """Derive class name from worksheet name if the sheet looks like a class."""
    s = sheet_name.strip()
    # Remove common suffixes like 半期成绩, 期末成绩, 成绩
    s = re.sub(r"(半期|期末|期中|月考|成绩|记分册|登记表)$", "", s).strip()
    # Normalize full-width parentheses
    s = s.replace("（", "(").replace("）", ")")
    return normalize_class_name(s)


def _class_name_from_title_row(df_raw: pd.DataFrame) -> str:
    """Try to extract class name from the first title row of a sheet.

    Some teacher-made score sheets put the class name in the sheet title row,
    e.g. '25计2班半期考试成绩'.
    """
    if df_raw.empty:
        return ""
    first_row = df_raw.iloc[0]
    row_text = " ".join(str(x) for x in first_row if pd.notna(x))
    # Look for patterns like 25计2班, 2025级电子2班
    m = re.search(r"(\d{2,4}(?:级)?[\u4e00-\u9fa5]{0,4}\d{1,3}班)", row_text)
    if m:
        return normalize_class_name(m.group(1))
    m = re.search(r"(\d{2,4}级[^成]{2,10}班)", row_text)
    if m:
        return normalize_class_name(m.group(1))
    return ""


def _looks_like_class_name(s: str) -> bool:
    """Check whether a string looks like a real class name."""
    if not s:
        return False
    s = s.strip()
    # Pure digits like '01班' are not informative enough
    if re.fullmatch(r"\d+班?", s):
        return False
    # Contains grade/major keywords
    if re.search(r"\d{2,4}级", s) or any(kw in s for kw in ["电子", "计算机", "数控", "汽车", "旅游", "保育", "茶艺", "运动", "机械", "汽修", "计", "数", "融通", "普高"]):
        return True
    return False


def _detect_class_category(class_name: str, grade_name: str, major_name: str) -> Dict[str, bool]:
    """Detect whether the class is a 普高班 or 职普融通班高一学期.

    Returns a dict with keys:
      - is_pugao: 班级属于普高班
      - is_zhipurongtong: 班级属于职普融通班
      - is_first_year: 年级为高一（通过 grade_name 或 class_name 判断）
      - has_science_humanities: 需要提取理化生政史地
    """
    text = f"{class_name} {grade_name} {major_name}"
    is_pugao = "普高" in text
    is_zhipurongtong = "融通" in text

    # 高一学期判断：年级名包含“高一”，或班级名以 25/26 等入学年份开头且处于高一学段。
    # 这里采用 grade_name/class_name 包含“高一”或“2025级”作为高一标识。
    grade_lower = str(grade_name).lower()
    class_lower = str(class_name).lower()
    is_first_year = (
        "高一" in grade_lower
        or "高一" in class_lower
        or re.search(r"202[5-9]级", grade_lower)
        or re.search(r"^25", class_name)
        or re.search(r"^26", class_name)
    )

    # 只有职普融通班的高一学期才需要单独提取理化生政史地
    has_science_humanities = is_pugao or (is_zhipurongtong and is_first_year)
    return {
        "is_pugao": is_pugao,
        "is_zhipurongtong": is_zhipurongtong,
        "is_first_year": is_first_year,
        "has_science_humanities": has_science_humanities,
    }


def _score_columns_for_subject(headers: List[str], subject_keywords: List[str]) -> List[int]:
    """Find score column indices for a subject, excluding rank/objective/subjective columns."""
    cols = []
    for i, h in enumerate(headers):
        if _header_excluded(h):
            continue
        if any(k in _normalize_header(h) for k in subject_keywords):
            cols.append(i)
    return cols


def _build_subject_column_map(headers: List[str], category: Dict[str, bool]) -> Dict[str, List[int]]:
    """Build a mapping from subject key to list of column indices.

    For professional courses, all non-language/science/humanities/rank columns
    are collected.
    """
    subject_map = {}

    # Always extract language subjects.
    for key in ["chinese", "math", "english"]:
        subject_map[key] = _score_columns_for_subject(headers, SUBJECT_KEYWORDS[key])

    # For 普高班 / 职普融通班高一学期, extract physics/chemistry/biology/politics/history/geography.
    if category.get("has_science_humanities"):
        for key in ["physics", "chemistry", "biology", "politics", "history", "geography"]:
            subject_map[key] = _score_columns_for_subject(headers, SUBJECT_KEYWORDS[key])

    # Professional subjects: all remaining columns that look like professional courses
    # or are not language/science/humanities/rank columns.
    professional_keywords = SUBJECT_KEYWORDS["professional"]
    professional_cols = []
    excluded_base = set()
    for key in ["chinese", "math", "english", "physics", "chemistry", "biology", "politics", "history", "geography"]:
        excluded_base.update(subject_map.get(key, []))

    # Rank columns should be excluded individually, not truncate remaining columns.
    excluded_indices = set()
    for i, h in enumerate(headers):
        if _header_excluded(h):
            excluded_indices.add(i)

    # Student identifier columns that should never be treated as scores.
    id_columns = {"", "序号", "姓名", "考号", "准考证号", "学号", "学籍号", "考生号", "报名号", "班级", "班级名称", "年级", "专业大类", "专业名称", "班主任", "教师"}

    for i, h in enumerate(headers):
        if i in excluded_indices:
            continue
        if i in excluded_base:
            continue
        norm = _normalize_header(h)
        # Skip pure metadata columns and unnamed placeholder columns
        if norm in id_columns:
            continue
        if norm.lower().startswith("unnamed"):
            continue
        if any(k in norm for k in professional_keywords):
            professional_cols.append(i)
        elif not category.get("has_science_humanities") and not _header_contains_any(h, SUBJECT_KEYWORDS["total"]):
            # For non-science-humanities classes, any remaining non-total score column
            # is treated as a professional subject.
            professional_cols.append(i)

    subject_map["professional"] = professional_cols
    return subject_map


def _resolve_multiheader_columns(df: pd.DataFrame) -> Tuple[List[str], Dict[str, List[int]], List[str], Dict[int, str]]:
    """Resolve MultiIndex columns into merged headers, subject map, professional sub-column names and column index to name mapping."""
    merged_headers = []
    # Group columns by top-level subject name
    subject_groups: Dict[str, List[Tuple[int, Tuple[Any, ...]]]] = {}
    for flat_idx, col in enumerate(df.columns):
        if isinstance(col, tuple):
            top = _normalize_header(col[0])
            sub = _normalize_header(col[1]) if len(col) > 1 else ""
        else:
            top = _normalize_header(col)
            sub = ""
        merged_headers.append(f"{top}_{sub}" if sub else top)
        if top:
            subject_groups.setdefault(top, []).append((flat_idx, col))

    subject_map: Dict[str, List[int]] = {}
    professional_sub_names: List[str] = []
    professional_name_map: Dict[int, str] = {}
    for key, keywords in SUBJECT_KEYWORDS.items():
        if key in ("total",):
            continue
        cols = []
        for top_name, entries in subject_groups.items():
            if any(k in top_name for k in keywords):
                # Prefer the "总分" sub-column for this subject
                total_idx = None
                other_idx = None
                for flat_idx, col in entries:
                    sub = _normalize_header(col[1]) if isinstance(col, tuple) and len(col) > 1 else ""
                    if sub in ("总分", "总得分", "总成绩"):
                        total_idx = flat_idx
                        break
                    if not _header_excluded(sub) and sub not in ("", "unnamed"):
                        other_idx = flat_idx
                    # 收集专业课子列名
                    if key == "professional":
                        sub_name = str(col[1]).strip() if isinstance(col, tuple) and len(col) > 1 else top_name
                        if sub_name:
                            professional_sub_names.append(sub_name)
                            professional_name_map[flat_idx] = sub_name
                chosen = total_idx if total_idx is not None else other_idx
                if chosen is not None:
                    cols.append(chosen)
        subject_map[key] = cols

    return merged_headers, subject_map, professional_sub_names, professional_name_map


def _extract_subject_scores(row: pd.Series, subject_map: Dict[str, List[int]], professional_names: Dict[int, str]) -> Dict[str, Any]:
    """Extract cleaned scores for each subject from a row.

    For language/science subjects, the first valid numeric value is used.
    For professional subjects, all valid numeric values are summed, and each
    individual subject score is also recorded.
    """
    scores = {}

    # Language and science/humanities: take first valid value.
    for key in ["chinese", "math", "english", "physics", "chemistry", "biology", "politics", "history", "geography"]:
        val = None
        for col_idx in subject_map.get(key, []):
            v = _clean_value(row.iloc[col_idx])
            if isinstance(v, (int, float)):
                val = float(v)
                break
            if isinstance(v, str):
                try:
                    val = float(v)
                    break
                except ValueError:
                    continue
        scores[key] = val

    # Professional: sum all valid values and keep per-subject scores.
    professional_total = 0.0
    has_professional = False
    professional_subject_scores = {}
    for idx, col_idx in enumerate(subject_map.get("professional", [])):
        v = _clean_value(row.iloc[col_idx])
        val = None
        if isinstance(v, (int, float)):
            val = float(v)
        elif isinstance(v, str):
            try:
                val = float(v)
            except ValueError:
                val = None
        if val is not None:
            professional_total += val
            has_professional = True
            name = professional_names.get(col_idx, f"专业课{idx + 1}")
            # Avoid duplicate names by appending index if necessary
            original_name = name
            counter = 1
            while name in professional_subject_scores:
                name = f"{original_name}({counter})"
                counter += 1
            professional_subject_scores[name] = val
    scores["professional"] = professional_total if has_professional else None
    scores["professional_subject_scores"] = professional_subject_scores

    return scores


def _extract_total_score(row: pd.Series, headers: List[str], subject_scores: Dict[str, Any]) -> Optional[float]:
    """Extract the total score column if present; otherwise fall back to sum of subjects."""
    total_cols = _score_columns_for_subject(headers, SUBJECT_KEYWORDS["total"])
    for col_idx in total_cols:
        v = _clean_value(row.iloc[col_idx])
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                continue

    # Fallback: sum all available subject scores.
    total = 0.0
    for key, val in subject_scores.items():
        if val is not None and isinstance(val, (int, float)):
            total += float(val)
    return total if total > 0 else None


def _extract_sheet(path_or_bytes, sheet_name: str, engine: Optional[str] = None, grade_prefix: str = "") -> List[Dict[str, Any]]:
    """Extract score records from a single worksheet."""
    # Read raw data without header to locate header rows
    if hasattr(path_or_bytes, "seek"):
        path_or_bytes.seek(0)
    df_raw = _read_with_engines(path_or_bytes, sheet_name=sheet_name, header=None, engine=engine)

    detail_row = _find_detail_header_row(df_raw)
    if detail_row is None:
        return []

    multi_header = False
    professional_sub_names_from_multiheader = []
    professional_name_map = {}
    # If there is a category row above the detail row, use multi-level headers
    if detail_row > 0 and _is_category_row(df_raw.iloc[detail_row - 1]):
        if hasattr(path_or_bytes, "seek"):
            path_or_bytes.seek(0)
        df = _read_with_engines(path_or_bytes, sheet_name=sheet_name, header=[detail_row - 1, detail_row], engine=engine)
        if isinstance(df.columns, pd.MultiIndex):
            multi_header = True
            headers, subject_map, professional_sub_names_from_multiheader, professional_name_map = _resolve_multiheader_columns(df)
        else:
            headers = [str(h) if pd.notna(h) else "" for h in df.columns]
            # We don't know category yet; build default map without class info
            category = {"has_science_humanities": False}
            subject_map = _build_subject_column_map(headers, category)
    else:
        if hasattr(path_or_bytes, "seek"):
            path_or_bytes.seek(0)
        df = _read_with_engines(path_or_bytes, sheet_name=sheet_name, header=detail_row, engine=engine)
        headers = [str(h) if pd.notna(h) else "" for h in df.columns]
        category = {"has_science_humanities": False}
        subject_map = _build_subject_column_map(headers, category)

    # Fallback: if too many unnamed/duplicate headers, try adjacent two rows
    if not multi_header:
        unnamed_ratio = sum(1 for h in headers if "Unnamed" in h) / max(len(headers), 1)
        if unnamed_ratio > 0.3 or len(set(headers)) < len(headers) * 0.7:
            try:
                if hasattr(path_or_bytes, "seek"):
                    path_or_bytes.seek(0)
                df_multi = _read_with_engines(path_or_bytes, sheet_name=sheet_name, header=[detail_row, detail_row + 1], engine=engine)
                if isinstance(df_multi.columns, pd.MultiIndex):
                    df = df_multi
                    headers, subject_map, professional_sub_names_from_multiheader, professional_name_map = _resolve_multiheader_columns(df)
                    multi_header = True
            except Exception:
                pass

    name_col = _match_column(headers, ["姓名"])
    # Exclude rank columns when locating class/grade/major columns.
    class_col = _match_column(headers, ["班级"], exclude=["排名"])
    grade_col = _match_column(headers, ["年级"], exclude=["排名"])
    major_col = _match_column(headers, ["专业"], exclude=["排名"])
    teacher_col = _match_column(headers, ["班主任", "教师"])
    student_no_col = _match_column(headers, STUDENT_ID_KEYWORDS, exclude=["排名"])

    if name_col is None:
        return []

    records = []
    inferred_class = _class_name_from_sheet(sheet_name)
    title_class = _class_name_from_title_row(df_raw)
    for row_idx, row in df.iterrows():
        name = _clean_value(row.iloc[name_col]) if name_col is not None else None
        if not name or not isinstance(name, str) or not name.strip():
            continue

        name = name.strip()

        # Skip aggregate/footer rows commonly found in score sheets.
        AGGREGATE_NAMES = {"平均分", "总分", "合计", "最高分", "最低分", "标准差", "优秀率", "及格率", "名次", "排名"}
        if name in AGGREGATE_NAMES or any(kw in name for kw in ("平均", "合计", "汇总")):
            continue

        class_name = _clean_value(row.iloc[class_col]) if class_col is not None else ""
        if isinstance(class_name, (int, float)):
            class_name = str(int(class_name)) if float(class_name).is_integer() else str(class_name)
        else:
            class_name = str(class_name).strip() if class_name else ""
        class_name = normalize_class_name(class_name)

        # 如果单元格班级名缺少年级前缀，使用文件名中的年级补全
        if grade_prefix and class_name and not re.search(r"\d{2,4}级", class_name):
            class_name = normalize_class_name(grade_prefix + class_name)

        # Prefer sheet name or title row when the cell class name is empty or uninformative
        if not _looks_like_class_name(class_name):
            if _looks_like_class_name(title_class):
                class_name = title_class
            elif _looks_like_class_name(inferred_class):
                class_name = inferred_class

        # 最终兜底：如果班级名仍缺少年级前缀，使用文件名中的年级补全
        if grade_prefix and class_name and not re.search(r"\d{2,4}级", class_name):
            class_name = normalize_class_name(grade_prefix + class_name)

        grade_name = _clean_value(row.iloc[grade_col]) if grade_col is not None else ""
        major_name = _clean_value(row.iloc[major_col]) if major_col is not None else ""
        if isinstance(grade_name, (int, float)):
            grade_name = str(int(grade_name)) if float(grade_name).is_integer() else str(grade_name)
        else:
            grade_name = str(grade_name).strip() if grade_name else ""
        if isinstance(major_name, (int, float)):
            major_name = str(int(major_name)) if float(major_name).is_integer() else str(major_name)
        else:
            major_name = str(major_name).strip() if major_name else ""

        category = _detect_class_category(class_name, grade_name, major_name)

        # Rebuild subject map with detected category when not using multi-header resolution
        if multi_header:
            # For multi-header, we already resolved subject columns; but we may need to
            # adjust professional vs science columns based on class type. Re-resolve
            # applying category knowledge by rebuilding from merged headers.
            headers, subject_map, professional_sub_names_from_multiheader, professional_name_map = _resolve_multiheader_columns(df)
            # After resolving by keywords, adjust professional/science split based on category.
            if not category.get("has_science_humanities"):
                # Move any science columns into professional if they exist.
                sci_cols = []
                for key in ["physics", "chemistry", "biology", "politics", "history", "geography"]:
                    sci_cols.extend(subject_map.get(key, []))
                    subject_map[key] = []
                if sci_cols:
                    subject_map["professional"] = list(dict.fromkeys(subject_map.get("professional", []) + sci_cols))
        else:
            subject_map = _build_subject_column_map(headers, category)
            professional_name_map = {col_idx: headers[col_idx] for col_idx in subject_map.get("professional", [])}

        subject_scores = _extract_subject_scores(row, subject_map, professional_name_map)
        total_score = _extract_total_score(row, headers, subject_scores)

        # Calculate language total and professional total
        language_total = 0.0
        for key in ["chinese", "math", "english"]:
            val = subject_scores.get(key)
            if val is not None:
                language_total += float(val)

        professional_total = subject_scores.get("professional")

        prof_subject_scores = subject_scores.get("professional_subject_scores", {})

        # 提取学号/准考证号
        student_no = ""
        if student_no_col is not None:
            raw_no = _clean_value(row.iloc[student_no_col])
            if raw_no is not None:
                if isinstance(raw_no, (int, float)):
                    student_no = str(int(raw_no)) if float(raw_no).is_integer() else str(raw_no)
                else:
                    student_no = str(raw_no).strip()

        record = {
            "row_index": int(row_idx) + 1,
            "name": name.strip(),
            "student_no": student_no,
            "class_name": class_name,
            "grade_name": grade_name,
            "major_name": major_name,
            "homeroom_teacher": _clean_value(row.iloc[teacher_col]) if teacher_col is not None else "",
            "语文": subject_scores.get("chinese"),
            "数学": subject_scores.get("math"),
            "英语": subject_scores.get("english"),
            "物理": subject_scores.get("physics"),
            "化学": subject_scores.get("chemistry"),
            "生物": subject_scores.get("biology"),
            "政治": subject_scores.get("politics"),
            "历史": subject_scores.get("history"),
            "地理": subject_scores.get("geography"),
            "专业课": professional_total,
            "专业课明细": list(prof_subject_scores.keys()),
            "professional_subject_scores": prof_subject_scores,
            "语数外总分": language_total if language_total > 0 else None,
            "总分": total_score,
        }

        # Normalize string fields
        for key in ["grade_name", "major_name", "homeroom_teacher"]:
            val = record[key]
            if val is None:
                record[key] = ""
            elif isinstance(val, (int, float)):
                record[key] = str(int(val)) if float(val).is_integer() else str(val)
            else:
                record[key] = str(val).strip()

        records.append(record)

    return records


# Aggregate sheet names that duplicate individual class sheets; skip them.
AGGREGATE_SHEET_NAMES = {"校班级成绩表", "班级成绩表", "汇总", "成绩汇总", "报告"}


def _extract_excel(path_or_bytes, filename: str = "") -> List[Dict[str, Any]]:
    """Extract records from all sheets of an Excel file."""
    if isinstance(path_or_bytes, bytes):
        path_or_bytes = io.BytesIO(path_or_bytes)
    sheets, engine = _list_sheets(path_or_bytes)
    grade_prefix = _extract_grade_from_filename(filename)
    records = []
    for sheet in sheets:
        if sheet in AGGREGATE_SHEET_NAMES:
            continue
        path_or_bytes.seek(0)
        sheet_records = _extract_sheet(path_or_bytes, sheet, engine=engine, grade_prefix=grade_prefix)
        for rec in sheet_records:
            rec["sheet_name"] = sheet
        records.extend(sheet_records)
    return records


def _extract_csv(content: bytes, filename: str = "") -> List[Dict[str, Any]]:
    """Extract records from a CSV file."""
    import csv
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    grade_prefix = _extract_grade_from_filename(filename)
    records = []
    for idx, row in enumerate(reader, start=2):
        record = {"row_index": idx}
        headers = list(row.keys())
        name_col = next((h for h in headers if "姓名" in h), None)
        class_col = next((h for h in headers if "班级" in h), None)
        grade_col = next((h for h in headers if "年级" in h), None)
        major_col = next((h for h in headers if "专业" in h), None)
        student_no_col = next((h for h in headers if any(k in h for k in STUDENT_ID_KEYWORDS)), None)

        record["name"] = str(row.get(name_col, "")).strip() if name_col else ""
        record["student_no"] = str(row.get(student_no_col, "")).strip() if student_no_col else ""
        raw_class_name = str(row.get(class_col, "")).strip() if class_col else ""
        class_name = normalize_class_name(raw_class_name)
        # 如果班级名缺少年级前缀，使用文件名中的年级补全
        if grade_prefix and class_name and not re.search(r"\d{2,4}级", class_name):
            class_name = normalize_class_name(grade_prefix + class_name)
        record["class_name"] = class_name
        record["grade_name"] = str(row.get(grade_col, "")).strip() if grade_col else ""
        record["major_name"] = str(row.get(major_col, "")).strip() if major_col else ""
        record["homeroom_teacher"] = ""

        class_name = record["class_name"]
        grade_name = record["grade_name"]
        major_name = record["major_name"]
        category = _detect_class_category(class_name, grade_name, major_name)
        subject_map = _build_subject_column_map(headers, category)

        # Convert CSV row to Series-like access
        class RowLike:
            def __init__(self, data):
                self.data = data
            def iloc(self, idx):
                return list(self.data.values())[idx]
        row_like = RowLike(row)

        # Build subject scores
        subject_scores = {}
        professional_subject_scores = {}
        for key in ["chinese", "math", "english", "physics", "chemistry", "biology", "politics", "history", "geography", "professional"]:
            total = 0.0
            has = False
            for h in headers:
                if any(k in _normalize_header(h) for k in SUBJECT_KEYWORDS.get(key, [])):
                    if _header_excluded(h):
                        continue
                    val = row.get(h)
                    try:
                        num = float(val) if val is not None and str(val).strip() != "" else None
                    except (ValueError, TypeError):
                        num = None
                    if num is not None:
                        if key == "professional":
                            total += num
                            has = True
                            # Collect individual professional subject score by header
                            sub_name = str(h).strip()
                            original_name = sub_name
                            counter = 1
                            while sub_name in professional_subject_scores:
                                sub_name = f"{original_name}({counter})"
                                counter += 1
                            professional_subject_scores[sub_name] = num
                        else:
                            subject_scores[key] = num
                            break
            if key == "professional" and has:
                subject_scores[key] = total

        language_total = sum(
            float(subject_scores.get(k, 0) or 0) for k in ["chinese", "math", "english"]
        )
        total_score = None
        total_col = next((h for h in headers if any(a in h for a in SUBJECT_KEYWORDS["total"])), None)
        if total_col:
            try:
                total_score = float(row.get(total_col))
            except (ValueError, TypeError):
                total_score = None
        if total_score is None:
            total_score = language_total + float(subject_scores.get("professional", 0) or 0)

        record.update({
            "语文": subject_scores.get("chinese"),
            "数学": subject_scores.get("math"),
            "英语": subject_scores.get("english"),
            "物理": subject_scores.get("physics"),
            "化学": subject_scores.get("chemistry"),
            "生物": subject_scores.get("biology"),
            "政治": subject_scores.get("politics"),
            "历史": subject_scores.get("history"),
            "地理": subject_scores.get("geography"),
            "专业课": subject_scores.get("professional"),
            "专业课明细": list(professional_subject_scores.keys()),
            "professional_subject_scores": professional_subject_scores,
            "语数外总分": language_total if language_total > 0 else None,
            "总分": total_score if total_score > 0 else None,
        })
        records.append(record)
    return records


def parse_score_file_with_meta(content: bytes, filename: str) -> Dict[str, Any]:
    """Parse Excel/CSV and return records plus detected subject metadata."""
    records = parse_score_file(content, filename)
    detected = {}
    professional_subjects = []

    for rec in records:
        # Public subjects
        for key, label in SUBJECT_LABELS.items():
            if key in ("total", "professional"):
                continue
            val = rec.get(label)
            if val is not None and isinstance(val, (int, float)):
                if label not in detected:
                    detected[label] = {"name": label, "type": "public"}

        # Professional sub-columns
        prof_details = rec.get("专业课明细") or []
        for name in prof_details:
            if not name or not isinstance(name, str):
                continue
            norm = _normalize_header(name)
            if not norm or norm.lower().startswith("unnamed"):
                continue
            if name not in professional_subjects:
                professional_subjects.append(name)

        # Aggregate professional
        prof_val = rec.get("专业课")
        if prof_val is not None and isinstance(prof_val, (int, float)):
            if "专业课" not in detected:
                detected["专业课"] = {"name": "专业课", "type": "professional"}

    # Default max scores
    default_max = {
        "语文": 150,
        "数学": 150,
        "英语": 100,
        "物理": 100,
        "化学": 100,
        "生物": 100,
        "政治": 100,
        "历史": 100,
        "地理": 100,
        "专业课": 100,
    }

    detected_subjects = []
    for label in ["语文", "数学", "英语", "物理", "化学", "生物", "政治", "历史", "地理", "专业课"]:
        if label in detected:
            detected_subjects.append({
                "name": label,
                "max_score": default_max.get(label, 100),
                "type": detected[label].get("type", "public"),
            })

    # Professional sub columns with auto-extracted max score.
    # Aggregate professional max score is the maximum per-class sum of sub-column
    # full marks, not the sum across all classes/records.
    prof_sub_list = []
    prof_max_by_name = {}
    for name in professional_subjects:
        max_score = _extract_max_score_from_header(name)
        if max_score is None:
            max_score = 100.0
        prof_max_by_name[name] = max_score
        prof_sub_list.append({
            "name": name,
            "max_score": max_score,
            "type": "professional_sub",
        })

    total_prof_max = 0.0
    if prof_sub_list:
        for rec in records:
            prof_details = rec.get("专业课明细") or []
            per_class_max = 0.0
            for name in prof_details:
                if not name or not isinstance(name, str):
                    continue
                norm = _normalize_header(name)
                if not norm or norm.lower().startswith("unnamed"):
                    continue
                per_class_max += prof_max_by_name.get(name, 100.0)
            if per_class_max > total_prof_max:
                total_prof_max = per_class_max

    # Update aggregate professional max score to the largest per-class sum.
    if prof_sub_list:
        for item in detected_subjects:
            if item["name"] == "专业课":
                item["max_score"] = total_prof_max if total_prof_max > 0 else 100.0

    return {
        "records": records,
        "detected_subjects": detected_subjects,
        "professional_subjects": prof_sub_list,
    }


def parse_score_file(content: bytes, filename: str) -> List[Dict[str, Any]]:
    """Parse Excel/CSV bytes into raw student-score records.

    Reads all worksheets for Excel files. Returns a list of records with
    standard keys: name, class_name, grade_name, major_name,
    homeroom_teacher, 语文, 数学, 英语, 物理, 化学, 生物, 政治, 历史, 地理,
    专业课, 语数外总分, 总分.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        return _extract_csv(content, filename=filename)
    return _extract_excel(content, filename=filename)
