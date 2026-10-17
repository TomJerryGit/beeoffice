@echo off
title BeeOffice Launcher
cd /d "%~dp0"

echo ============================================
echo   BeeOffice Launcher
echo ============================================
echo.

REM 显示当前目录，便于排查
echo Current directory: %CD%
echo.

REM 检查 beeoffice 包是否存在
if not exist "beeoffice\main.py" (
    echo [ERROR] Cannot find "beeoffice\main.py" in the current directory.
    echo.
    echo Possible reasons:
    echo   1. This script is not placed in the project root directory
    echo   2. The "beeoffice" folder was renamed or moved
    echo.
    echo Project root should look like:
    echo   run.bat
    echo   requirements.txt
    echo   beeoffice\
    echo     main.py
    echo     app.py
    echo     ...
    echo.
    pause
    exit /b 1
)

REM 检查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM 检查依赖
python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo [INFO] PySide6 not found. Installing dependencies...
    echo.
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies.
        echo Please run manually: python -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

REM 显式添加当前目录到 PYTHONPATH
set PYTHONPATH=%~dp0;%PYTHONPATH%

REM 启动
echo Starting BeeOffice...
echo.
python -m beeoffice.main

if errorlevel 1 (
    echo.
    echo [WARN] Program exited with code %errorlevel%
    echo Log directory: %USERPROFILE%\.beeoffice_logs
    echo.
)

pause