@echo off
chcp 65001 >nul
cd /d "%~dp0backend"

python -c "import uvicorn" 2>nul
if errorlevel 1 (
    echo 正在安装依赖...
    python -m pip install -r requirements.txt
)

echo 启动成绩管理系统后端服务...
echo API 文档: http://localhost:8000/docs
echo 前端页面: http://localhost:8000/pages/dashboard.html

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
