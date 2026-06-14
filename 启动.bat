@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 光伏IV曲线分析系统
echo ============================================================
echo       光伏材料实验室 - IV曲线分析系统 v1.0
echo ============================================================
echo.

REM 先检测 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python 环境！
    echo 请先安装 Python 3.9+ 并添加到 PATH
    echo 下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM 检查依赖
python -c "import PyQt6, numpy, scipy, matplotlib, pandas, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo [提示] 首次运行，正在安装依赖库...
    echo.
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动执行:
        echo    pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo [启动] 正在启动...
echo.
python main.py %*
if errorlevel 1 (
    echo.
    echo [异常] 程序异常退出，错误码 %ERRORLEVEL%
    echo.
    pause
)
