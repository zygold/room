# 考试成绩导入时设置学科满分 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让成绩导入支持为当次考试设置各科满分，专业课支持多门子课程汇总，导入阶段不换算、仅记录原始分与满分配置。

**Architecture:** 新增 `exam_subject_configs` 表保存每次考试的科目满分；`import_files` 新增 `subject_config` 字段暂存用户设置；解析器从表头自动提取满分并返回检测到的科目；确认导入时将配置写入考试；换算逻辑改为读取考试配置作为原始满分。

**Tech Stack:** FastAPI + SQLite + Pandas + vanilla JS + Tailwind CSS

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `backend/database.py` | 新增 `exam_subject_configs` 表和 `import_files.subject_config` 迁移 |
| `backend/services/excel_parser.py` | 从表头提取满分；返回检测到的科目及专业课子课程信息 |
| `backend/routers/import_scores.py` | 上传/校验/确认接口接收并保存 `subject_config` |
| `backend/services/score_converter.py` | 换算时使用 `exam_subject_configs` 的满分 |
| `pages/data-import.html` | 上传表单默认满分 + 确认弹窗动态编辑检测到的科目 |

---

## Task 1: 数据库迁移

**Files:**
- Modify: `backend/database.py`

- [ ] **Step 1: 在 SCHEMA_SQL 中新增 `exam_subject_configs` 表**

在 `subject_standards` 表定义之后、`scores` 表定义之前插入：

```sql
-- 考试科目满分配置表
CREATE TABLE IF NOT EXISTS exam_subject_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    subject_name TEXT NOT NULL,
    max_score REAL NOT NULL,
    UNIQUE(exam_id, subject_name),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);
```

- [ ] **Step 2: 在 migrations 列表中新增 `import_files.subject_config` 字段**

```python
migrations = [
    ...
    ("import_files", "subject_config TEXT"),
]
```

- [ ] **Step 3: 验证数据库初始化无报错**

Run: `cd backend && python -c "from database import init_db; init_db(); print('ok')"`
Expected: `ok`

---

## Task 2: Excel 解析器提取满分与检测科目

**Files:**
- Modify: `backend/services/excel_parser.py`

- [ ] **Step 1: 新增 `_extract_max_score_from_header` 辅助函数**

在 `_normalize_header` 函数之后插入：

```python
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
```

- [ ] **Step 2: 让 `_resolve_multiheader_columns` 同时返回专业课子列名**

修改函数签名和返回逻辑：

```python
def _resolve_multiheader_columns(df: pd.DataFrame) -> Tuple[List[str], Dict[str, List[int]], List[str]]:
    """Resolve MultiIndex columns into merged headers, subject map, and professional sub-column names."""
    merged_headers = []
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
    for key, keywords in SUBJECT_KEYWORDS.items():
        if key in ("total",):
            continue
        cols = []
        for top_name, entries in subject_groups.items():
            if any(k in top_name for k in keywords):
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
                    if key == "professional" and sub:
                        professional_sub_names.append(str(col[1]).strip() if isinstance(col, tuple) and len(col) > 1 else top_name)
                chosen = total_idx if total_idx is not None else other_idx
                if chosen is not None:
                    cols.append(chosen)
        subject_map[key] = cols

    return merged_headers, subject_map, professional_sub_names
```

- [ ] **Step 3: 修改 `_extract_sheet` 使用新的返回值并记录专业课子列名**

在 `_extract_sheet` 中，把原来的：

```python
if isinstance(df.columns, pd.MultiIndex):
    multi_header = True
    headers, subject_map = _resolve_multiheader_columns(df)
else:
    ...
```

改为：

```python
professional_sub_names_from_multiheader = []
if isinstance(df.columns, pd.MultiIndex):
    multi_header = True
    headers, subject_map, professional_sub_names_from_multiheader = _resolve_multiheader_columns(df)
else:
    ...
```

在构建 `record` 之前，把 single-header 下的 `prof_names` 逻辑调整为通用逻辑：

找到这段代码：

```python
# For single-header sheets, collect professional subject names for debugging.
if not multi_header:
    prof_names = []
    for col_idx in subject_map.get("professional", []):
        prof_names.append(_normalize_header(headers[col_idx]))
    record["专业课明细"] = prof_names
```

替换为：

```python
# Collect professional subject column names for display/editing full marks.
if multi_header:
    record["专业课明细"] = professional_sub_names_from_multiheader
else:
    prof_names = []
    for col_idx in subject_map.get("professional", []):
        raw_header = headers[col_idx]
        prof_names.append(str(raw_header).strip() if raw_header else "")
    record["专业课明细"] = prof_names
```

- [ ] **Step 4: 新增 `parse_score_file_with_meta` 函数**

在文件末尾 `parse_score_file` 函数之前或之后插入：

```python
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

    # Professional sub columns with auto-extracted max score
    prof_sub_list = []
    total_prof_max = 0.0
    for name in professional_subjects:
        max_score = _extract_max_score_from_header(name)
        if max_score is None:
            max_score = 100.0
        total_prof_max += max_score
        prof_sub_list.append({
            "name": name,
            "max_score": max_score,
            "type": "professional_sub",
        })

    # Update aggregate professional max score to sum of sub columns if any
    if prof_sub_list:
        for item in detected_subjects:
            if item["name"] == "专业课":
                item["max_score"] = total_prof_max

    return {
        "records": records,
        "detected_subjects": detected_subjects,
        "professional_subjects": prof_sub_list,
    }
```

- [ ] **Step 5: 运行解析器 smoke test**

Run: `cd backend && python -c "from services.excel_parser import parse_score_file_with_meta; print('ok')"`
Expected: `ok`

---

## Task 3: 上传接口接收满分配置

**Files:**
- Modify: `backend/routers/import_scores.py`

- [ ] **Step 1: 修改 `upload_file` 接收 `subject_config` 并保存**

在函数签名新增参数：

```python
subject_config: Optional[str] = Form(None),
```

在 `INSERT INTO import_files` 的 SQL 和参数中加入 `subject_config`：

```python
cur = conn.execute(
    "INSERT INTO import_files (file_name, grade_id, major_id, exam_type, school_year, semester, month, student_count, validation_status, subject_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (file.filename, grade_id, major_id, exam_type, school_year, semester, month, 0, "待校验", subject_config, now_str()),
)
```

- [ ] **Step 2: 修改 `upload_multiple_files` 同样接收并保存 `subject_config`**

```python
subject_config: Optional[str] = Form(None),
```

```python
cur = conn.execute(
    "INSERT INTO import_files (file_name, grade_id, major_id, exam_type, school_year, semester, month, student_count, validation_status, subject_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (upload.filename, grade_id, major_id, exam_type, school_year, semester, month, 0, "待校验", subject_config, now_str()),
)
```

---

## Task 4: 校验接口返回检测到的科目

**Files:**
- Modify: `backend/routers/import_scores.py`
- Modify: `backend/services/excel_parser.py`（已在 Task 2 完成）

- [ ] **Step 1: 在 import_scores.py 顶部引入 `parse_score_file_with_meta`**

```python
from services.excel_parser import parse_score_file, normalize_class_name, _read_with_engines, _clean_value, parse_score_file_with_meta
```

- [ ] **Step 2: 新增 `_load_records_with_meta` 辅助函数**

在 `_load_records` 函数之后插入：

```python
def _load_records_with_meta(file_row: sqlite3.Row):
    """Load parsed records and detected subject metadata from a saved file."""
    saved_path = file_row["file_path"] or _find_saved_file_legacy(file_row)
    if not saved_path or not Path(saved_path).exists():
        raise HTTPException(status_code=404, detail="服务器文件已丢失")

    content = Path(saved_path).read_bytes()
    filename = file_row["file_name"]
    return parse_score_file_with_meta(content, filename)
```

- [ ] **Step 3: 修改 `validate_file` 返回 `detected_subjects` 和 `professional_subjects`**

把：

```python
records = _load_records(row)
```

改为：

```python
meta = _load_records_with_meta(row)
records = meta["records"]
```

在 `return` 之前加入：

```python
# 合并用户上传时携带的 subject_config 默认值（如果有）
user_config = {}
if row["subject_config"]:
    try:
        import json
        user_config = json.loads(row["subject_config"])
    except Exception:
        pass

detected_subjects = meta.get("detected_subjects", [])
professional_subjects = meta.get("professional_subjects", [])

# 用用户上传时的配置覆盖默认满分
for item in detected_subjects + professional_subjects:
    name = item["name"]
    if name in user_config:
        try:
            item["max_score"] = float(user_config[name].get("max_score", item["max_score"]))
        except (ValueError, AttributeError):
            pass
```

在 `return` 字典中加入：

```python
"detected_subjects": detected_subjects,
"professional_subjects": professional_subjects,
```

---

## Task 5: 确认导入接口保存考试满分配置

**Files:**
- Modify: `backend/routers/import_scores.py`

- [ ] **Step 1: 在 `ConfirmImport` 和 `ConfirmBatchImport` 模型中新增 `subject_config`**

```python
class ConfirmImport(BaseModel):
    exam_name: str
    exam_date: Optional[str] = None
    school_year: Optional[str] = None
    semester: Optional[str] = None
    month: Optional[int] = None
    merge_exam_id: Optional[int] = None
    subject_config: Optional[Dict[str, Dict[str, float]]] = None


class ConfirmBatchImport(BaseModel):
    file_ids: List[int]
    exam_name: str
    exam_date: Optional[str] = None
    school_year: Optional[str] = None
    semester: Optional[str] = None
    month: Optional[int] = None
    merge_exam_id: Optional[int] = None
    subject_config: Optional[Dict[str, Dict[str, float]]] = None
```

- [ ] **Step 2: 新增 `_save_exam_subject_configs` 辅助函数**

在 `_update_class_grade_counts` 之后插入：

```python
import json


def _build_default_subject_config(major_id: Optional[int]):
    """Build default subject config from system standards."""
    config = {}
    with get_db() as conn:
        rows = conn.execute("SELECT subject_name, major_id, max_score FROM subject_standards").fetchall()
    for r in rows:
        if r["major_id"] is None:
            config.setdefault(r["subject_name"], {"max_score": r["max_score"]})
        elif r["major_id"] == major_id:
            config[r["subject_name"]] = {"max_score": r["max_score"]}
    # Ensure core subjects exist
    for subj, default in [("语文", 150), ("数学", 150), ("英语", 100), ("专业课", 100)]:
        if subj not in config:
            config[subj] = {"max_score": default}
    return config


def _save_exam_subject_configs(conn, exam_id: int, subject_config: Optional[Dict[str, Dict[str, float]]], major_id: Optional[int]):
    """Save subject full-mark config for an exam."""
    if not subject_config:
        subject_config = _build_default_subject_config(major_id)

    # Normalize and validate
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
        conn.execute(
            """INSERT INTO exam_subject_configs (exam_id, subject_name, max_score)
               VALUES (?, ?, ?)
               ON CONFLICT(exam_id, subject_name) DO UPDATE SET max_score=?""",
            (exam_id, name, max_score, max_score),
        )
```

- [ ] **Step 3: 在 `confirm_import` 创建/合并考试后调用保存配置**

在 `batch = f"{payload.exam_name}_{exam_id}"` 之前插入：

```python
_save_exam_subject_configs(conn, exam_id, payload.subject_config, major_id)
```

- [ ] **Step 4: 在 `confirm_batch_import` 同样调用保存配置**

在 `batch = f"{payload.exam_name}_{exam_id}"` 之前插入：

```python
_save_exam_subject_configs(conn, exam_id, payload.subject_config, major_id)
```

---

## Task 6: 换算逻辑使用考试满分配置

**Files:**
- Modify: `backend/services/score_converter.py`

- [ ] **Step 1: 新增读取考试配置的辅助函数**

在 `get_subject_standards` 之后插入：

```python
def get_exam_subject_configs(exam_id: int) -> Dict[str, float]:
    """Return subject_name -> max_score mapping for an exam."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT subject_name, max_score FROM exam_subject_configs WHERE exam_id=?",
            (exam_id,),
        ).fetchall()
    return {r["subject_name"]: r["max_score"] for r in rows}
```

- [ ] **Step 2: 修改 `convert_scores` 使用考试配置作为原始满分**

把：

```python
chinese_c = convert_score(r["chinese_score"], target.get("原始语文满分", 150), target["语文"])
math_c = convert_score(r["math_score"], target.get("原始数学满分", 150), target["数学"])
english_c = convert_score(r["english_score"], target.get("原始英语满分", 100), target["英语"])
prof_c = convert_score(r["professional_score"], r["professional_max_score"] or 100, prof_max)
```

改为：

```python
exam_cfg = get_exam_subject_configs(exam_id)

chinese_c = convert_score(r["chinese_score"], exam_cfg.get("语文", 150), target["语文"])
math_c = convert_score(r["math_score"], exam_cfg.get("数学", 150), target["数学"])
english_c = convert_score(r["english_score"], exam_cfg.get("英语", 100), target["英语"])
prof_c = convert_score(r["professional_score"], exam_cfg.get("专业课", r["professional_max_score"] or 100), prof_max)
```

---

## Task 7: 启动后端并验证 API

**Files:**
- 无代码修改

- [ ] **Step 1: 启动后端服务**

Run: `cd backend && python main.py`
Expected: Server starts on `http://localhost:8000`

- [ ] **Step 2: 使用 Swagger 或 curl 测试 `/import/validate/{id}` 返回 detected_subjects**

Run: `curl http://localhost:8000/import/files` 获取一个 file_id，然后：

```bash
curl -X POST http://localhost:8000/import/validate/1
```

Expected: JSON 中包含 `detected_subjects` 和 `professional_subjects`

---

## Task 8: 前端上传表单增加满分设置区域

**Files:**
- Modify: `pages/data-import.html`

- [ ] **Step 1: 在考试类型/学年/学期表单下方插入「学科满分设置」区域**

在 `</div>`（月份选择 div 结束）之后、<!-- ====== 2. Two Tab Sections ====== --> 之前插入：

```html
        <!-- ====== 学科满分设置 ====== -->
        <div class="rounded-lg border p-6" style="background-color: var(--card); border-color: var(--border);">
          <div class="flex items-center justify-between mb-4">
            <h3 style="font-size: 15px; font-weight: 600; color: var(--foreground);">学科满分设置（可选）</h3>
            <span style="font-size: 12px; color: var(--muted-foreground);">导入时设置当次考试各科满分，未设置则使用系统默认值</span>
          </div>
          <div id="subject-config-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <!-- 动态生成 -->
          </div>
          <p id="subject-config-tip" class="mt-3" style="font-size: 12px; color: var(--muted-foreground);">选择专业后可自动加载专业课默认满分。</p>
        </div>
```

- [ ] **Step 2: 在 JS 中新增学科满分配置状态与渲染函数**

在 `let scoreFilesData = [];` 之后添加：

```javascript
let subjectConfig = {
  "语文": { max_score: 150 },
  "数学": { max_score: 150 },
  "英语": { max_score: 100 },
  "专业课": { max_score: 100 },
};
let professionalSubConfig = {}; // name -> { max_score }
```

在 `loadSettings` 函数中，加载完年级专业后调用加载学科标准：

```javascript
async function loadSubjectStandards() {
  try {
    const standards = await apiGet('/subject-standards');
    const majorId = uploadMajor.value ? parseInt(uploadMajor.value, 10) : null;
    const defaults = { "语文": 150, "数学": 150, "英语": 100, "专业课": 100 };
    standards.forEach(s => {
      if (s.major_id === null) {
        defaults[s.subject_name] = s.max_score;
      } else if (s.major_id === majorId) {
        defaults[s.subject_name] = s.max_score;
      }
    });
    for (const [name, max] of Object.entries(defaults)) {
      if (!subjectConfig[name]) subjectConfig[name] = { max_score: max };
      else subjectConfig[name].max_score = max;
    }
    renderSubjectConfig();
  } catch (e) {
    console.warn('加载学科标准失败', e);
  }
}
```

在 `loadSettings` 末尾添加事件监听和初始化：

```javascript
uploadMajor.addEventListener('change', loadSubjectStandards);
loadSubjectStandards();
```

新增渲染函数：

```javascript
function renderSubjectConfig() {
  const grid = document.getElementById('subject-config-grid');
  const majorId = uploadMajor.value ? parseInt(uploadMajor.value, 10) : null;
  let html = '';
  const core = ['语文', '数学', '英语'];
  core.forEach(name => {
    const cfg = subjectConfig[name] || { max_score: 100 };
    html += renderSubjectInput(name, cfg.max_score);
  });
  if (majorId) {
    html += renderSubjectInput('专业课', subjectConfig['专业课']?.max_score || 100);
  }
  grid.innerHTML = html;
  document.getElementById('subject-config-tip').style.display = majorId ? 'none' : 'block';
}

function renderSubjectInput(name, value) {
  return `<div class="flex items-center gap-2">
    <label style="font-size: 13px; color: var(--foreground); white-space: nowrap;">${name}</label>
    <input type="number" min="0" step="1" data-subject="${name}" value="${value}" class="subject-max-input w-full rounded-md border px-3 py-2" style="border-color: var(--border); background-color: var(--card); color: var(--foreground); font-size: 14px;">
    <span style="font-size: 12px; color: var(--muted-foreground); white-space: nowrap;">分</span>
  </div>`;
}

function collectSubjectConfig() {
  const inputs = document.querySelectorAll('.subject-max-input');
  const cfg = {};
  inputs.forEach(input => {
    const name = input.dataset.subject;
    const val = parseFloat(input.value);
    if (name && !isNaN(val) && val > 0) {
      cfg[name] = { max_score: val };
    }
  });
  return cfg;
}
```

- [ ] **Step 3: 上传时携带 `subject_config`**

在 `doUpload` 函数中，在 `if (uploadMonth.value) form.append('month', uploadMonth.value);` 之后添加：

```javascript
const cfg = collectSubjectConfig();
form.append('subject_config', JSON.stringify(cfg));
```

---

## Task 9: 确认弹窗动态编辑检测到的科目满分

**Files:**
- Modify: `pages/data-import.html`

- [ ] **Step 1: 在确认弹窗的表单中插入「本次考试科目满分」区域**

在「合并到已有考试」div 之后、「考试日期」div 之前插入：

```html
          <div>
            <label style="font-size: 13px; color: var(--muted-foreground); display:block; margin-bottom: 0.25rem;">本次考试科目满分</label>
            <div id="confirm-subject-config" class="rounded-md border p-3 space-y-2" style="border-color: var(--border); background-color: var(--muted);">
              <p style="font-size: 12px; color: var(--muted-foreground);">请先校验文件以加载检测到的科目。</p>
            </div>
          </div>
```

- [ ] **Step 2: 新增弹窗内科目配置的渲染与编辑逻辑**

在 JS 中新增变量：

```javascript
let confirmSubjectConfig = {};
let confirmProfessionalSubjects = [];
```

新增渲染函数：

```javascript
function renderConfirmSubjectConfig() {
  const container = document.getElementById('confirm-subject-config');
  if (!currentValidation || !currentValidation.detected_subjects) {
    container.innerHTML = '<p style="font-size: 12px; color: var(--muted-foreground);">请先校验文件以加载检测到的科目。</p>';
    return;
  }

  let html = '<div class="grid grid-cols-2 gap-3">';
  const detected = currentValidation.detected_subjects || [];
  const profSubs = currentValidation.professional_subjects || [];

  detected.forEach(item => {
    const val = confirmSubjectConfig[item.name]?.max_score ?? item.max_score;
    if (item.name === '专业课' && profSubs.length > 0) {
      // 显示汇总，只读
      html += `<div class="flex items-center gap-2">
        <span style="font-size: 13px; color: var(--foreground); white-space: nowrap;">${item.name}（汇总）</span>
        <input type="number" readonly data-confirm-subject="${item.name}" value="${val}" class="confirm-subject-max w-full rounded-md border px-2 py-1" style="border-color: var(--border); background-color: var(--color-neutral-100); color: var(--foreground); font-size: 13px;">
        <span style="font-size: 12px; color: var(--muted-foreground);">分</span>
      </div>`;
    } else {
      html += `<div class="flex items-center gap-2">
        <span style="font-size: 13px; color: var(--foreground); white-space: nowrap;">${item.name}</span>
        <input type="number" min="0" step="1" data-confirm-subject="${item.name}" value="${val}" class="confirm-subject-max w-full rounded-md border px-2 py-1" style="border-color: var(--border); background-color: var(--card); color: var(--foreground); font-size: 13px;">
        <span style="font-size: 12px; color: var(--muted-foreground);">分</span>
      </div>`;
    }
  });
  html += '</div>';

  if (profSubs.length > 0) {
    html += '<div class="mt-3 pt-3 border-t" style="border-color: var(--border);"><p style="font-size: 12px; color: var(--muted-foreground); margin-bottom: 0.5rem;">专业课子课程（修改后汇总自动更新）</p><div class="grid grid-cols-2 gap-3">';
    profSubs.forEach(item => {
      const val = confirmProfessionalSubjects.find(s => s.name === item.name)?.max_score ?? item.max_score;
      html += `<div class="flex items-center gap-2">
        <span style="font-size: 12px; color: var(--foreground); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${item.name}">${item.name}</span>
        <input type="number" min="0" step="1" data-prof-sub="${item.name}" value="${val}" class="confirm-prof-sub-max w-full rounded-md border px-2 py-1" style="border-color: var(--border); background-color: var(--card); color: var(--foreground); font-size: 13px;">
        <span style="font-size: 12px; color: var(--muted-foreground);">分</span>
      </div>`;
    });
    html += '</div></div>';
  }

  container.innerHTML = html;

  // Bind input events
  container.querySelectorAll('.confirm-prof-sub-max').forEach(input => {
    input.addEventListener('input', updateConfirmProfessionalTotal);
  });
}

function updateConfirmProfessionalTotal() {
  const inputs = document.querySelectorAll('.confirm-prof-sub-max');
  let total = 0;
  inputs.forEach(input => {
    const val = parseFloat(input.value);
    if (!isNaN(val) && val > 0) total += val;
  });
  const aggInput = document.querySelector('[data-confirm-subject="专业课"]');
  if (aggInput) aggInput.value = total;
}

function collectConfirmSubjectConfig() {
  const cfg = {};
  document.querySelectorAll('.confirm-subject-max').forEach(input => {
    const name = input.dataset.confirmSubject;
    const val = parseFloat(input.value);
    if (name && !isNaN(val) && val > 0) {
      cfg[name] = { max_score: val };
    }
  });
  document.querySelectorAll('.confirm-prof-sub-max').forEach(input => {
    const name = input.dataset.profSub;
    const val = parseFloat(input.value);
    if (name && !isNaN(val) && val > 0) {
      cfg[name] = { max_score: val };
    }
  });
  return cfg;
}
```

- [ ] **Step 3: 在 `renderValidation` 成功后调用渲染**

在 `renderValidation` 函数末尾 `fixDataBtn.disabled = ...` 之后添加：

```javascript
// 初始化确认弹窗的满分配置
if (result.detected_subjects) {
  confirmSubjectConfig = {};
  result.detected_subjects.forEach(item => {
    confirmSubjectConfig[item.name] = { max_score: item.max_score };
  });
  confirmProfessionalSubjects = result.professional_subjects || [];
  renderConfirmSubjectConfig();
}
```

- [ ] **Step 4: 在 `openConfirm` 打开弹窗时重新渲染**

在 `openConfirm` 函数末尾 `confirmModal.style.display = 'flex';` 之前添加：

```javascript
renderConfirmSubjectConfig();
```

---

## Task 10: 确认导入请求携带 `subject_config`

**Files:**
- Modify: `pages/data-import.html`

- [ ] **Step 1: 修改 `submitConfirmBtn` 点击事件**

把构造 `basePayload` 的部分：

```javascript
const basePayload = {
  exam_name: name,
  exam_date: confirmExamDate.value || null,
  school_year: confirmSchoolYear.value,
  semester: confirmSemester.value,
  month: month,
  merge_exam_id: mergeExamId,
};
```

改为：

```javascript
const subjectConfig = collectConfirmSubjectConfig();
const basePayload = {
  exam_name: name,
  exam_date: confirmExamDate.value || null,
  school_year: confirmSchoolYear.value,
  semester: confirmSemester.value,
  month: month,
  merge_exam_id: mergeExamId,
  subject_config: subjectConfig,
};
```

---

## Task 11: 数据表格预览显示「语文（150）」格式

**Files:**
- Modify: `pages/data-import.html`

- [ ] **Step 1: 在确认弹窗中增加预览表头（可选，用于展示）**

此任务可选。如果确认弹窗内已有足够信息，可跳过。如需在成绩管理页面也显示满分，需要后端 `/api/scores` 返回 `exam_subject_configs` 并在 `score-management.html` 中渲染。本计划暂不做，聚焦于导入流程。

---

## Task 12: 批量导入使用第一个文件的配置

**Files:**
- Modify: `pages/data-import.html`

- [ ] **Step 1: 批量模式下从第一个已选文件获取配置**

批量导入的确认弹窗目前没有执行校验步骤，因此无法直接拿到 `detected_subjects`。简化处理：批量模式使用上传表单中设置的 `subject_config`，与单个文件模式一致。在 `batchImportBtn` 点击事件中，`renderConfirmSubjectConfig` 会显示上传表单中的配置（无 detected_subjects 时显示默认值）。

如需要更精确的批量配置，可先对第一个文件调用 `/import/validate/{id}` 获取 detected_subjects。本计划保持简单：批量导入沿用上传表单默认值。

---

## Task 13: 端到端测试

**Files:**
- 无代码修改

- [ ] **Step 1: 准备测试用 Excel**

创建一个包含以下列的成绩表：姓名、班级、语文、数学、英语、电子元器件检测与识别（100分）、电子电工基础（100分）、总分。

- [ ] **Step 2: 上传并校验**

在页面上传文件，选择专业，点击校验。

Expected:
- 校验报告出现
- 确认弹窗的「本次考试科目满分」显示：语文 150、数学 150、英语 100、专业课（汇总）200、电子元器件检测与识别 100、电子电工基础 100

- [ ] **Step 3: 修改满分后确认导入**

把语文改为 120，点击确认导入。

Expected:
- 导入成功
- 数据库 `exam_subject_configs` 中该考试的 `语文` 记录 `max_score` = 120

- [ ] **Step 4: 验证换算使用考试配置**

调用奖学金评选或换算接口，验证转换分按 120 分制换算。

Run: `curl -X POST http://localhost:8000/api/scores/convert?exam_id=<exam_id>`
Expected: 返回转换的记录数， chinese_converted 按 120 分制换算

---

## 自我检查

- [ ] Spec coverage: 数据库表、上传配置、校验返回、确认保存、换算使用、前端表单/弹窗均已覆盖
- [ ] Placeholder scan: 无 TBD/TODO/"实现 later" / 无 "添加适当错误处理" 等模糊描述
- [ ] Type consistency: `subject_config` 统一为 `Dict[str, Dict[str, float]]`，解析器返回的 `detected_subjects` 字段名一致
- [ ] Backward compatibility: 旧文件无 `subject_config` 时 fallback 到系统标准
