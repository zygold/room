import requests

base = "http://localhost:8000"

def check(name, r, expect_status=(200,)):
    ok = r.status_code in expect_status
    print(f"{'✓' if ok else '✗'} {name}: {r.status_code}")
    if not ok:
        print(f"   响应: {r.text[:200]}")
    return ok

results = []

# P0: 基础数据与导入
results.append(check("首页", requests.get(base + "/")))
results.append(check("年级列表", requests.get(base + "/api/grades")))
results.append(check("专业列表", requests.get(base + "/api/majors")))
results.append(check("班级类别", requests.get(base + "/api/class-types")))
results.append(check("班级列表", requests.get(base + "/api/classes")))
results.append(check("学生列表", requests.get(base + "/api/students", params={"page": 1, "limit": 5})))
results.append(check("导入文件列表", requests.get(base + "/api/import/files")))

# P1: 成绩、换算、奖学金、导出
results.append(check("成绩列表", requests.get(base + "/api/scores", params={"page": 1, "page_size": 5})))
results.append(check("考试列表", requests.get(base + "/api/scores/exams")))

exams = requests.get(base + "/api/scores/exams").json()
if exams:
    exam_id = exams[0]["id"]
    results.append(check("考试科目满分配置读取", requests.get(base + f"/api/scores/exam-subject-configs/{exam_id}")))
    results.append(check("考试科目满分配置写入", requests.post(base + f"/api/scores/exam-subject-configs/{exam_id}", json={"configs": {"语文": 150, "数学": 150, "英语": 100, "专业课": 100}})))

grades = requests.get(base + "/api/grades").json()
class_types = requests.get(base + "/api/class-types").json()
if grades and class_types and exams:
    payload = {
        "grade_id": grades[0]["id"],
        "class_type_ids": [ct["id"] for ct in class_types],
        "exam_ids": [exams[0]["id"]],
        "category": "本科方向班",
        "options": {"special_top_language_first_prize": True},
    }
    results.append(check("奖学金筛选", requests.post(base + "/api/scholarship/run-screen", json=payload)))

results.append(check("奖学金候选列表", requests.get(base + "/api/scholarship/candidates", params={"page": 1, "page_size": 5})))
results.append(check("奖学金统计", requests.get(base + "/api/scholarship/stats")))

export_payload = {
    "export_type": "学生成绩明细",
    "filter_condition": {},
    "format": "xlsx",
    "options": {"split_by_class": True},
}
results.append(check("导出生成", requests.post(base + "/api/export/generate", json=export_payload)))
results.append(check("导出历史", requests.get(base + "/api/export/history")))

# P2: 备份还原、仪表盘
results.append(check("仪表盘统计", requests.get(base + "/api/dashboard/stats")))
results.append(check("仪表盘最近操作", requests.get(base + "/api/dashboard/recent-ops")))
results.append(check("仪表盘待办", requests.get(base + "/api/dashboard/tasks")))
results.append(check("备份配置读取", requests.get(base + "/api/backup/config")))
results.append(check("备份配置更新", requests.put(base + "/api/backup/config", json={"retention_days": 30})))
results.append(check("备份列表", requests.get(base + "/api/backup/list")))
results.append(check("备份存储信息", requests.get(base + "/api/backup/storage")))

# P3: 日志
results.append(check("日志列表", requests.get(base + "/api/logs/", params={"page": 1, "page_size": 5})))
results.append(check("日志类型", requests.get(base + "/api/logs/types")))
results.append(check("日志导出", requests.get(base + "/api/logs/export", params={"fmt": "xlsx"})))

print(f"\n回归测试完成: {sum(results)}/{len(results)} 通过")
if not all(results):
    raise SystemExit(1)
