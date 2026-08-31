import requests

base = "http://localhost:8000"

# 1. 仪表盘统计
r = requests.get(base + "/api/dashboard/stats")
print(f"仪表盘统计: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  统计: {data.get('counts')}")
    print(f"  换算率: {data.get('conversion_rate')}%")

# 2. 最近操作
r = requests.get(base + "/api/dashboard/recent-ops", params={"limit": 5})
print(f"最近操作: {r.status_code} 条数={len(r.json().get('items', []))}")

# 3. 待办任务
r = requests.get(base + "/api/dashboard/tasks")
print(f"待办任务: {r.status_code} 条数={len(r.json().get('items', []))}")

# 4. 备份配置
r = requests.get(base + "/api/backup/config")
print(f"备份配置读取: {r.status_code} {r.json()}")

r = requests.put(base + "/api/backup/config", json={"after_import": True, "retention_days": 30})
print(f"备份配置更新: {r.status_code} {r.json()}")

# 5. 创建备份
r = requests.post(base + "/api/backup/create", json={"backup_type": "手动备份", "description": "P2 测试备份"})
print(f"创建备份: {r.status_code} {r.json()}")
backup_id = r.json().get("id") if r.status_code == 200 else None

# 6. 备份列表
r = requests.get(base + "/api/backup/list")
backups = r.json()
print(f"备份列表: {r.status_code} 条数={len(backups)}")

# 7. 恢复预览
if backup_id:
    r = requests.get(base + f"/api/backup/restore-preview/{backup_id}")
    print(f"恢复预览: {r.status_code} {r.json()}")

# 8. 存储信息
r = requests.get(base + "/api/backup/storage")
print(f"存储信息: {r.status_code} {r.json()}")

print("P2 基础测试完成")
