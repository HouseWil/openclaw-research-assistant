@echo off
REM ============================================================
REM OpenClaw Research Assistant - Start Script (Windows)
REM ============================================================
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo   ___                  ____ _
echo  / _ \  _ __   ___ _ __/ ___^| ^| __ ___      __
echo ^| ^| ^| ^| '_ \ / _ \ '_ \___ \ ^|/ _` \ \ /\ / /
echo ^| ^|_^| ^| ^|_) ^|  __/ ^| ^| ^|__) ^| ^| (_^| ^|\ V  V /
echo  \___/^| .__/ \___^|_^| ^|_____/^|_^\__,_^| \_/\_/
echo        ^|_^|   科研助手 v1.0.0
echo.

REM ── Check Python ──────────────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 未找到，请先安装 Python 3.9+
    echo         下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ── Install/check dependencies ────────────────────────────
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 正在安装依赖包...
    python -m pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [ERROR] 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
    echo [OK] 依赖安装完成
) else (
    echo [OK] 依赖已就绪
)

echo.
python install.py %*
pause
