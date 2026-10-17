@echo off
REM 双击即可运行：绕过 PowerShell 执行策略，调用 push_github.ps1
REM 用法：push_github.bat [远程名] [分支名]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push_github.ps1" %*
pause
