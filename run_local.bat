@echo off
REM ============================================================
REM  BeeOffice local launcher (Windows)
REM
REM  Usage:
REM    run_local.bat              start BeeOffice
REM    run_local.bat --install    install runtime deps from requirements.lock
REM    run_local.bat --check      check Python/deps without starting GUI
REM    run_local.bat --venv       create .venv (Python 3.11) and use it
REM ============================================================
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title BeeOffice Local Launcher
cd /d "%~dp0"

set "INSTALL=0"
set "CHECK=0"
set "CREATE_VENV=0"
for %%A in (%*) do (
    if /I "%%~A"=="--install" set "INSTALL=1"
    if /I "%%~A"=="--check" set "CHECK=1"
    if /I "%%~A"=="--venv" set "CREATE_VENV=1"
)

echo ============================================================
echo   BeeOffice local launcher
echo ============================================================
echo   Project: %CD%
echo.

if not exist "beeoffice\main.py" (
    echo [ERROR] beeoffice\main.py not found.
    echo         Run this script from the BeeOffice project root.
    pause
    exit /b 1
)

REM ---------- select interpreter ----------
set "PY="
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else if "%CREATE_VENV%"=="1" (
    echo [INFO] Creating .venv with Python 3.11...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.11 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        pause
        exit /b 1
    )
    set "PY=.venv\Scripts\python.exe"
)

if not defined PY (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found.
        echo         Install Python 3.11 x64 and enable "Add Python to PATH".
        echo         Then run: run_local.bat --venv
        pause
        exit /b 1
    )
    set "PY=python"
)

echo [INFO] Python: %PY%
"%PY%" --version
if errorlevel 1 (
    echo [ERROR] Cannot run Python.
    pause
    exit /b 1
)

REM ---------- version check ----------
"%PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [ERROR] BeeOffice requires Python 3.11 or newer for this build.
    echo         Recommended: py -3.11 -m venv .venv
    echo         Then: run_local.bat --venv --install
    pause
    exit /b 1
)

REM ---------- dependencies ----------
"%PY%" -c "import PySide6" >nul 2>nul
if errorlevel 1 set "NEED_DEPS=1"
if not defined NEED_DEPS "%PY%" -c "import pandas" >nul 2>nul
if errorlevel 1 set "NEED_DEPS=1"

if defined NEED_DEPS (
    if "%INSTALL%"=="1" (
        echo [INFO] Installing runtime dependencies...
        if exist "requirements.lock" (
            "%PY%" -m pip install --require-hashes -r requirements.lock
        ) else (
            "%PY%" -m pip install -r requirements.txt
        )
        if errorlevel 1 (
            echo [ERROR] Dependency install failed.
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] Missing runtime dependencies.
        echo         Run: run_local.bat --install
        echo         Or:  "%PY%" -m pip install --require-hashes -r requirements.lock
        pause
        exit /b 1
    )
)

if "%CHECK%"=="1" (
    "%PY%" -c "import PySide6, pandas; from beeoffice.__version__ import __version__; print('OK', __version__)"
    if errorlevel 1 (
        echo [ERROR] Dependency check failed.
        pause
        exit /b 1
    )
    echo [OK] Python and dependencies are ready.
    exit /b 0
)

REM ---------- launch ----------
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%CD%;%PYTHONPATH%"
set "QT_AUTO_SCREEN_SCALE_FACTOR=1"

echo.
echo [INFO] Starting BeeOffice...
echo.
"%PY%" -m beeoffice.main
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [WARN] BeeOffice exited with code %EXIT_CODE%.
    echo        Logs: %USERPROFILE%\.beeoffice_logs
    pause
)

exit /b %EXIT_CODE%
