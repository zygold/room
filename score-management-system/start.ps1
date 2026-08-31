# 成绩管理系统启动脚本
$ErrorActionPreference = "Stop"
$BackendDir = Join-Path $PSScriptRoot "backend"

Set-Location $BackendDir

# 检查 Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "未找到 python，请安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

# 检查依赖（简单判断 uvicorn 是否存在）
$uvicorn = python -c "import uvicorn; print(uvicorn.__file__)" 2>$null
if (-not $uvicorn) {
    Write-Host "正在安装依赖..." -ForegroundColor Cyan
    python -m pip install -r requirements.txt
}

Write-Host "启动成绩管理系统后端服务..." -ForegroundColor Green
Write-Host "API 文档: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "前端页面: http://localhost:8000/pages/dashboard.html" -ForegroundColor Cyan

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
