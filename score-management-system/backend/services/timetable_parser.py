"""双课表解析：按 pandas 多引擎读取；兼容旧契约（两列布局）与真实布局（星期网格）。

旧契约：每 Sheet=班级，表头'科目/任课教师'，第2行起数据。
真实布局：第4行星期表头，第5行起网格，单元格'科目(合班)N\n教师'（教师可为空或被截断）。
"""
import hashlib
import io
import re

import pandas as pd

# 兼容两种包导入方式：从 backend 目录启动 或 从项目根目录启动
try:
    from services.excel_parser import _read_with_engines
except ImportError:  # pragma: no cover - 作为 backend.services 子模块被导入时
    from backend.services.excel_parser import _read_with_engines

WEEKDAYS = {"星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"}


# ---------------------------------------------------------------------------
# IO 层：统一使用 pandas 多引擎读取，不再直接依赖 xlrd/openpyxl/文件路径
# ---------------------------------------------------------------------------
def _read_sheets(content: bytes):
    return _read_with_engines(io.BytesIO(content), sheet_name=None, header=None)


def _convert_cell(v):
    """把 pandas 读取的单元格还原为接近原 Excel 的类型；NaN 转为 None。"""
    if pd.isna(v):
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _df_iter_rows(df):
    for _, row in df.iterrows():
        yield [_convert_cell(v) for v in row.tolist()]


# 常见文化课/公共课科目关键词，用于单元格顺序自适应判断
_COMMON_SUBJECTS = {
    "语文", "数学", "英语", "政治", "历史", "地理", "物理", "化学", "生物",
    "体育", "音乐", "美术", "信息技术", "通用技术", "劳动", "班会", "自习",
    "早自习", "晚自习", "心理", "生涯", "礼仪", "军事", "茶艺", "汽车文化",
    "幼儿早期学习与支持", "保育员职业素养", "历史与社会",
}


# ---------------------------------------------------------------------------
# 从原 normalizer.py 移植的纯文本归一化函数（引擎内不再访问数据库）
# ---------------------------------------------------------------------------
def normalize_name(raw):
    """全角→半角括号、去空格与首尾空白，得到可比对的标准形态。"""
    if not raw:
        return ""
    t = str(raw).replace("　", "").replace(" ", "")
    t = t.replace("（", "(").replace("）", ")")
    return t.strip()


def fingerprint(name):
    """归一化指纹 = MD5(标准形态)，用于班级档案唯一匹配。"""
    return hashlib.md5(normalize_name(name).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 单元格/表头工具函数
# ---------------------------------------------------------------------------
def _clean_subject(text):
    """'语文(合班)1' → '语文'；去合班标记与空白。"""
    if not text:
        return ""
    t = re.sub(r"[（(]?合班[）)]?\d*", "", str(text))
    return t.strip()


def _class_title(text):
    """班级名归一化，去掉截断残留括号（如 '23级电子3班(特优)('）。"""
    return normalize_name(text).strip("(（")


def _is_weekday_header(row):
    return sum(1 for c in row if str(c or "").strip() in WEEKDAYS) >= 3


def _is_legacy_header(row):
    heads = {str(c or "").strip() for c in row}
    return ("科目" in heads and "任课教师" in heads) or ("班级" in heads and "科目" in heads)


def _looks_like_subject(text, subject_names=None):
    """判断文本是否像科目名（命中已知科目集合或包含常见科目关键词）。"""
    if not text:
        return False
    std = normalize_name(text)
    if subject_names and std in {normalize_name(s) for s in subject_names}:
        return True
    # 合并同类词：去除“课”后缀再匹配
    base = re.sub(r"课$", "", std)
    return std in _COMMON_SUBJECTS or base in _COMMON_SUBJECTS


def _looks_like_teacher(text, teacher_names=None):
    """判断文本是否像教师名（命中教师课表 Sheet 名白名单）。"""
    if not text:
        return False
    std = normalize_name(text)
    if teacher_names and std in {normalize_name(t) for t in teacher_names}:
        return True
    return False


def _split_cell(cell, teacher_names=None, subject_names=None):
    """按换行分割单元格为 (科目, 教师)。

    支持两种常见排版：科目
教师、教师
科目。
    若顺序相反（上半部分像教师名、下半部分像科目名），自动交换。
    """
    text = str(cell or "").strip()
    # 统一各类换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        return None
    subject_part, _, teacher_part = text.rpartition("\n")
    subject_part = _clean_subject(subject_part.strip())
    teacher_part = teacher_part.strip()
    if not subject_part or not teacher_part:
        return None
    top_is_subject = _looks_like_subject(subject_part, subject_names)
    top_is_teacher = _looks_like_teacher(subject_part, teacher_names)
    bottom_is_subject = _looks_like_subject(teacher_part, subject_names)
    bottom_is_teacher = _looks_like_teacher(teacher_part, teacher_names)
    # 顺序明显相反：上半是教师名、下半是科目名，则交换
    if top_is_teacher and bottom_is_subject and not (top_is_subject or bottom_is_teacher):
        return teacher_part, subject_part
    return subject_part, teacher_part


# ---------------------------------------------------------------------------
# 主解析函数
# ---------------------------------------------------------------------------
def parse_class_timetable(content: bytes, teacher_names=None, subject_names=None):
    """班级视角三元组 [(班级标准形态, 科目, 教师原始名), ...]：旧契约+真实布局双兼容。"""
    triples = []
    sheets = _read_sheets(content)
    for sn in sheets.keys():
        rows = list(_df_iter_rows(sheets[sn]))
        if not rows:
            continue
        if _is_legacy_header(rows[0]):
            for r in rows[1:]:
                if len(r) >= 2 and r[0] and r[1]:
                    triples.append((normalize_name(sn),
                                    str(r[0]).strip(), str(r[1]).strip()))
            continue
        start = next((i for i, r in enumerate(rows) if _is_weekday_header(r)), None)
        if start is None:
            continue
        for ri in range(start + 1, len(rows)):
            for cell in rows[ri]:
                hit = _split_cell(cell, teacher_names, subject_names)
                if hit and hit[0] and hit[1]:
                    triples.append((_class_title(sn), hit[0], hit[1]))
    return triples


def parse_class_timetable_detailed(content: bytes, teacher_names=None, subject_names=None):
    """真实布局明细 [(班级标准形态, 科目, 教师原始名, 槽位'行:列')]，用于合班分组。"""
    out = []
    sheets = _read_sheets(content)
    for sn in sheets.keys():
        rows = list(_df_iter_rows(sheets[sn]))
        start = next((i for i, r in enumerate(rows) if _is_weekday_header(r)), None)
        if start is None:
            continue
        for ri in range(start + 1, len(rows)):
            for ci, cell in enumerate(rows[ri]):
                hit = _split_cell(cell, teacher_names, subject_names)
                if hit and hit[0] and hit[1]:
                    out.append((_class_title(sn), hit[0], hit[1], f"{ri}:{ci}"))
    return out


def parse_teacher_timetable(content: bytes):
    """教师视角三元组：旧契约+真实布局（教师名=Sheet名；合班占位与截断班级跳过）。"""
    triples = []
    sheets = _read_sheets(content)
    for sn in sheets.keys():
        rows = list(_df_iter_rows(sheets[sn]))
        teacher = normalize_name(sn)
        if not rows:
            continue
        if _is_legacy_header(rows[0]):
            for r in rows[1:]:
                if len(r) >= 2 and r[0] and r[1]:
                    triples.append((normalize_name(str(r[0])),
                                    str(r[1]).strip(), teacher))
            continue
        start = next((i for i, r in enumerate(rows) if _is_weekday_header(r)), None)
        if start is None:
            continue
        for ri in range(start + 1, len(rows)):
            for cell in rows[ri]:
                hit = _split_cell(cell)
                if not hit or not hit[0]:
                    continue
                subject, class_part = hit
                if class_part.startswith("合班"):
                    continue
                triples.append((normalize_name(class_part), subject, teacher))
    return triples


def teacher_names(content: bytes):
    """教师课表的全量教师标准名（用于教师名截断的前缀匹配与交叉提醒）。"""
    sheets = _read_sheets(content)
    return [normalize_name(sn) for sn in sheets.keys()]


def cross_validate(class_view, teacher_view):
    """旧契约严格交叉校验（对称差）；保留供合成样例与既有流程使用。"""
    return sorted(set(class_view) ^ set(teacher_view))


def resolve_teacher_prefix(raw, names):
    """教师名精确匹配 → 前缀匹配（截断场景，如 '夏'→'夏玲慧'）→ None。"""
    std = normalize_name(raw)
    if std in names:
        return std
    for n in names:
        if n.startswith(std) or std.startswith(n):
            return n
    return None


_HEAD_TEACHER_RE = re.compile(r"班主任[：:]\s*(.+)")


def extract_head_teachers(content: bytes, teacher_names=None):
    """从班级课表各 Sheet 的表头区域扫描'班主任：XXX'，返回 {班级标准名: 教师名}。

    若未直接命中班主任标注，退而取该班'班会'课程的教师作为班主任。
    """
    mapping = {}
    sheets = _read_sheets(content)
    for sn in sheets.keys():
        cls = _class_title(sn)
        rows = list(_df_iter_rows(sheets[sn]))
        if not rows:
            continue
        # 1) 直接扫描表头区域（前 12 行）
        for r in rows[:12]:
            for cell in r:
                text = str(cell or "").strip()
                m = _HEAD_TEACHER_RE.search(text)
                if m:
                    mapping[cls] = m.group(1).strip()
                    break
            if cls in mapping:
                break
        # 2) 退而求其次：班会课程教师
        if cls not in mapping:
            for r in rows:
                for cell in r:
                    hit = _split_cell(cell, teacher_names, subject_names={"班会"})
                    if hit and hit[0] == "班会" and hit[1]:
                        mapping[cls] = hit[1]
                        break
                if cls in mapping:
                    break
    return mapping
