import requests

base = "http://localhost:8000"

# 测试首页
r = requests.get(base + "/")
print(f"首页: {r.status_code} {r.json()}")

# 测试成绩列表
r = requests.get(base + "/api/scores", params={"page": 1, "page_size": 5})
print(f"成绩列表: {r.status_code} 记录数={len(r.json().get('items', []))} 总数={r.json().get('total', 0)}")

# 测试班级列表
r = requests.get(base + "/api/classes")
print(f"班级列表: {r.status_code} 班级数={len(r.json())}")

# 测试学生表包含 student_no
r = requests.get(base + "/api/scores", params={"keyword": "周欣怡", "page": 1, "page_size": 5})
if r.status_code == 200:
    data = r.json().get("items", [])
    if data:
        print(f"第一条成绩记录字段: {list(data[0].keys())}")

print("API 基础测试完成")
