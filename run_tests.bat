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

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

python -c "import pytest" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing dev dependencies...
    python -m pip install -r requirements-dev.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dev dependencies.
        pause
        exit /b 1
    )
)

echo Running full test suite with coverage...
echo.

pytest tests/ ^
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