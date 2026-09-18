@echo off
chcp 65001 >nul
title 成绩管理系统 - Web Server v1.0

cd /d "%~dp0"

REM === Python 自检 ===
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未检测到 Python, 请先安装 Python 3.10+
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] 首次运行, 正在安装依赖...
    python -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo [ERROR] 依赖安装失败, 请手动执行: pip install -r backend\requirements.txt
        pause
        exit /b 1
    )
)

REM === 端口检测 ===
set PORT=8766
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo [WARN] 端口 %PORT% 已被进程 PID=%%a 占用
    choice /C YN /M "  强制终止该进程"
    if errorlevel 2 (
        echo 用户取消, 启动中止
        pause
        exit /b 0
    )
    taskkill /PID %%a /F >nul 2>&1
    timeout /t 2 /nobreak >nul
)

REM === 启动 ===
cd backend
echo.
echo ================================
echo  成绩管理系统 启动中...
echo  本地访问: http://127.0.0.1:%PORT%/pages/login.html
echo  局域网:  http://0.0.0.0:%PORT%
echo  默认账户: admin / admin123
echo ================================
echo.

python -m uvicorn main:app --host 0.0.0.0 --port %PORT%

if errorlevel 1 (
    echo.
    echo [ERROR] 启动失败, 请检查上方日志
    pause
)
