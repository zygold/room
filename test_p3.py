import requests

base = "http://localhost:8000"

# 1. 日志列表
r = requests.get(base + "/api/logs/", params={"page": 1, "page_size": 5})
print(f"日志列表: {r.status_code} 总数={r.json().get('total')} 条数={len(r.json().get('items', []))}")

# 2. 按类型筛选
r = requests.get(base + "/api/logs/types")
print(f"日志类型: {r.status_code} {r.json()}")

r = requests.get(base + "/api/logs/", params={"operation_type": "奖学金筛选", "page_size": 5})
print(f"奖学金筛选日志: {r.status_code} 总数={r.json().get('total')}")

# 3. 日志导出 xlsx
r = requests.get(base + "/api/logs/export", params={"fmt": "xlsx"})
print(f"日志导出 xlsx: {r.status_code} 大小={len(r.content)} bytes")

# 4. 日志导出 csv
r = requests.get(base + "/api/logs/export", params={"fmt": "csv"})
print(f"日志导出 csv: {r.status_code} 大小={len(r.content)} bytes")

# 5. 清理 365 天前日志（保留全部）
r = requests.post(base + "/api/logs/cleanup", json={"days": 365})
print(f"日志清理: {r.status_code} {r.json()}")

print("P3 基础测试完成")
