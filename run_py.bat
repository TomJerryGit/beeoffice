@echo off
REM 自动找 Python 并执行传入的脚本
setlocal

set PY_EXE=

REM 常见安装位置，按顺序尝试
for %%P in (
    "D:\Program Files\Python311\python.exe"
    "D:\Program Files\Python311\Lib\venv\scripts\nt\python.exe"
    "D:\PyCharm\yootk\venv\Scripts\python.exe"
) do (
    if exist %%P (
        set PY_EXE=%%P
        goto :found
    )
)

REM 兜底：PATH 里找
where python >nul 2>nul
if not errorlevel 1 (
    set PY_EXE=python
    goto :found
)

echo [ERROR] 找不到 Python，请手动修改本脚本里的路径
pause
exit /b 1

:found
echo 使用: %PY_EXE%
"%PY_EXE%" %*