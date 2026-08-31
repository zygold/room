import requests

base = "http://localhost:8000"

# 1. 考试科目满分配置
exams = requests.get(base + "/api/scores/exams").json()
print(f"考试数: {len(exams)}")
if exams:
    exam_id = exams[0]["id"]
    configs = {"语文": 150, "数学": 150, "英语": 100, "专业课": 100}
    r = requests.post(base + f"/api/scores/exam-subject-configs/{exam_id}", json={"configs": configs})
    print(f"配置满分: {r.status_code} {r.json()}")
    r = requests.get(base + f"/api/scores/exam-subject-configs/{exam_id}")
    print(f"读取满分: {r.status_code} {r.json()}")

# 2. 奖学金评定：本科方向班，测试语数外年级第1名特评
classes = requests.get(base + "/api/classes").json()
class_types = requests.get(base + "/api/class-types").json()
grades = requests.get(base + "/api/grades").json()
print(f"班级类别: {[ct['name'] for ct in class_types]}")
print(f"年级: {[g['name'] for g in grades]}")

if grades and class_types and exams:
    grade_id = grades[0]["id"]
    class_type_ids = [ct["id"] for ct in class_types]
    exam_ids = [e["id"] for e in exams]
    payload = {
        "grade_id": grade_id,
        "class_type_ids": class_type_ids,
        "exam_ids": exam_ids[:1],
        "category": "本科方向班",
        "options": {"use_converted_scores": False, "special_top_language_first_prize": True},
    }
    r = requests.post(base + "/api/scholarship/run-screen", json=payload)
    print(f"奖学金筛选: {r.status_code} {r.json()}")

    r = requests.get(base + "/api/scholarship/candidates", params={"award_level": "一等奖"})
    data = r.json()
    print(f"一等奖候选: {data.get('total', 0)} 人")

# 3. 数据导出：按班级分文件
payload = {
    "export_type": "学生成绩明细",
    "filter_condition": {"grade_id": grades[0]["id"]} if grades else {},
    "format": "xlsx",
    "options": {"split_by_class": True, "include_converted": False},
}
r = requests.post(base + "/api/export/generate", json=payload)
print(f"导出生成: {r.status_code} {r.json()}")

print("P1 基础测试完成")
