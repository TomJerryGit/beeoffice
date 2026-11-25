@echo off
REM ============================================================
REM  BeeOffice local build (uses isolated venv when present)
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PY="
if defined BEEOFFICE_VENV if exist "%BEEOFFICE_VENV%\Scripts\python.exe" set "PY=%BEEOFFICE_VENV%\Scripts\python.exe"
if not defined PY if exist "..\ci-env\Scripts\python.exe" set "PY=..\ci-env\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found.
        exit /b 1
    )
    set "PY=python"
)

echo [INFO] Python: %PY%
"%PY%" --version
"%PY%" -c "import PySide6; print('PySide6', PySide6.__version__)"

for /f "tokens=2 delims== " %%V in ('findstr /b "__version__" beeoffice\__version__.py') do set "VER=%%~V"
set "VER=%VER:"=%"
if not defined VER (
    echo [ERROR] Cannot read version.
    exit /b 1
)
echo [INFO] Version: %VER%

"%PY%" build.py
if errorlevel 1 (
    echo [ERROR] build failed.
    exit /b 1
)

"%PY%" tools\package_release.py --version "%VER%"
if errorlevel 1 (
    echo [ERROR] zip failed.
    exit /b 1
)

"%PY%" tools\build_installer.py --skip-build
if errorlevel 1 (
    echo [ERROR] installer failed.
    exit /b 1
)

echo [OK] Build finished.
endlocal
