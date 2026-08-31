# 考试成绩导入时设置学科满分

## 背景与问题

当前成绩导入后，系统默认按固定满分进行换算：语文 150、数学 150、英语 100、专业课按 `professional_max_score` 100。但实际考试中各科满分并不固定，例如：

- 某次考试语文满分 120、数学满分 100
- 专业课可能由多门课程组成，如「电子元器件检测与识别（100分）」+「电子电工基础（100分）」，汇总后专业课满分为 200 分

如果导入时不记录当次考试的真实满分，后续统一标准分析或奖学金评选时换算结果会失真。

## 目标

1. 导入成绩时允许为当次考试设置各学科满分
2. 专业课支持多门子课程求和，汇总显示为「专业课（200分）」
3. 导入阶段**不自动换算**，成绩按原始分入库；换算留到奖学金评选、成绩统一分析等场景按需调用
4. 兼容旧数据，无配置时 fallback 到系统 `subject_standards`

## 方案概述

采用新增 `exam_subject_configs` 表记录每次考试的学科满分。解析文件时识别检测到的科目（含专业课子课程），在确认导入弹窗中按「科目名（满分）」形式展示并允许修改。

## 数据模型

### 新增表 `exam_subject_configs`

```sql
CREATE TABLE IF NOT EXISTS exam_subject_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    subject_name TEXT NOT NULL,        -- 语文/数学/英语/物理/化学/生物/政治/历史/地理/专业课/具体专业课列名
    max_score REAL NOT NULL,           -- 该科目本次考试满分
    UNIQUE(exam_id, subject_name),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);
```

说明：
- 语文、数学、英语、物理等公共课直接记录
- 专业课同时记录两类：
  - 各具体专业课列（如「电子元器件检测与识别」）的满分
  - 汇总后的「专业课」满分（等于各子课程满分之和）

### 现有表扩展

`import_files` 表新增 `subject_config` 字段（JSON 文本，可为空），用于在上传后、确认导入前暂存用户设置的满分：

```sql
ALTER TABLE import_files ADD COLUMN subject_config TEXT;
```

示例内容：
```json
{
  "语文": {"max_score": 120},
  "数学": {"max_score": 100},
  "英语": {"max_score": 100},
  "电子元器件检测与识别": {"max_score": 100},
  "电子电工基础": {"max_score": 100},
  "专业课": {"max_score": 200}
}
```

## 后端 API 改动

### 1. 上传接口增加满分配置

`/import/upload` 与 `/import/upload-multi` 增加可选表单字段：

- `subject_config`: JSON 字符串，格式同上

上传时存入 `import_files.subject_config`。

### 2. 校验接口返回检测到的科目

`/import/validate/{file_id}` 返回新增字段：

```json
{
  "status": "校验通过",
  "records": 45,
  "detected_subjects": [
    {"name": "语文", "max_score": 150},
    {"name": "数学", "max_score": 150},
    {"name": "英语", "max_score": 100},
    {"name": "电子元器件检测与识别", "max_score": 100},
    {"name": "电子电工基础", "max_score": 100},
    {"name": "专业课", "max_score": 200}
  ],
  "errors": [],
  "warnings": []
}
```

专业课子课程满分优先从表头提取（如「电子元器件检测与识别（100分）」），提取失败默认 100；汇总专业课满分自动计算为子课程满分之和。

### 3. 确认导入接口接收并保存满分

`/import/confirm/{file_id}` 与 `/import/confirm-batch` 接收 `subject_config`，在创建 `exams` 记录后，将配置写入 `exam_subject_configs`。

如果传入的 `subject_config` 为空，则按系统 `subject_standards` 生成默认配置。

### 4. 换算接口使用考试配置

`services/score_converter.py` 的 `convert_scores(exam_id, ...)` 改为：

1. 查询 `exam_subject_configs` 中该考试的配置
2. 对每门科目，使用 `exam_subject_configs.max_score` 作为原始满分
3. 目标满分仍从系统 `subject_standards` 读取
4. 没有考试配置时，fallback 到现有逻辑（语文/数学 150，英语 100，专业课 100）

## 前端交互

### 1. 上传表单区域

在现有年级、专业、考试类型等字段下方新增「学科满分设置（可选）」区域：

- 默认根据所选专业从 `/api/subject-standards` 加载系统标准
- 未选专业时，公共课仍显示默认值（语文 150、数学 150、英语 100），专业课隐藏或显示占位提示
- 每个科目一行：科目名 | 满分输入框
- 满分支持小数

### 2. 确认导入弹窗

校验通过后打开确认弹窗：

- 顶部显示考试名称、日期、学年学期等原有字段
- 中间新增「本次考试科目满分」区域
- 根据 `detected_subjects` 动态列出科目
- 专业课子课程分组显示，底部显示汇总后的「专业课（XXX分）」
- 表头预览同步显示为「语文（150）」「数学（150）」「英语（100）」「专业课（200）」格式
- 满分可编辑；专业课子课程修改后，汇总行自动更新

### 3. 批量导入

批量确认弹窗：
- 以第一个文件的 `subject_config` 作为默认
- 弹窗中统一修改后，应用到本次创建的所有考试（每个考试独立保存一份 `exam_subject_configs`）

## 成绩入库规则

- 语文、数学、英语等公共课：原始分直接存入对应字段
- 专业课：各子课程分数求和后存入 `professional_score`
- 总分：
  - 若成绩表提供「总分」列，优先使用
  - 否则按已识别科目分数求和
- `is_converted` 初始为 0，表示尚未换算

## 兼容与降级

- 旧考试无 `exam_subject_configs` 记录时，换算 fallback 到系统标准
- 旧导入文件无 `subject_config` 时，确认导入按系统标准生成配置
- 新增字段通过 `init_db` 的 lightweight migrations 自动添加

## 错误处理

- 满分输入为空或非数字：提示「请输入有效满分」
- 满分设为 0 或负数：提示「满分必须大于 0」
- 某科目在配置中缺失：使用系统标准并记录警告
- 校验接口检测到文件无成绩记录：返回明确错误

## 验收标准

- [ ] 上传成绩文件后，确认弹窗能显示检测到的科目及其默认满分
- [ ] 用户可修改各科满分，专业课子课程修改后汇总自动更新
- [ ] 导入后 `exam_subject_configs` 正确保存
- [ ] 奖学金评选/成绩统一分析调用换算时，使用考试配置的满分
- [ ] 旧考试/旧文件无配置时，行为与现有系统一致
- [ ] 导入阶段不自动换算，`scores.is_converted` 保持为 0
