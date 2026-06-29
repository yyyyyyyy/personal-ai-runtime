@echo off
REM Install git hooks without changing PowerShell execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_hooks.ps1"
exit /b %ERRORLEVEL%
