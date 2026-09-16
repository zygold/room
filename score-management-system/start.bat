@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
echo 启动成绩管理系统...
python -m uvicorn main:app --host 127.0.0.1 --port 8766 --reload
pause
