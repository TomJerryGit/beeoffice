@echo off
REM ============================================================
REM  BeeOffice 全量测试 + 覆盖率
REM ------------------------------------------------------------
REM  日常调试单文件请直接用：
REM      pytest tests/xxx.py -v
REM  （默认无覆盖率，秒级返回）
REM ============================================================
cd /d "%~dp0"

echo ============================================
echo   BeeOffice Test Suite
echo ============================================
echo.

set "PY="
if defined BEEOFFICE_VENV if exist "%BEEOFFICE_VENV%\Scripts\python.exe" set "PY=%BEEOFFICE_VENV%\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "..\ci-env\Scripts\python.exe" set "PY=..\ci-env\Scripts\python.exe"
if not defined PY (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found.
        pause
        exit /b 1
    )
    set "PY=python"
)

echo [INFO] Python: %PY%
"%PY%" -c "import pytest" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing dev dependencies...
    "%PY%" -m pip install -r requirements-dev.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dev dependencies.
        pause
        exit /b 1
    )
)

echo Running full test suite with coverage...
echo.

"%PY%" -m pytest tests/ ^
    --cov=beeoffice ^
    --cov-report=term-missing:skip-covered ^
    --cov-report=xml ^
    --cov-fail-under=25

if errorlevel 1 (
    echo.
    echo [WARN] Test suite completed with failures or low coverage.
    echo Log:      tests\pytest.log
    echo Coverage: coverage.xml
) else (
    echo.
    echo [OK] All tests passed.
)

pause