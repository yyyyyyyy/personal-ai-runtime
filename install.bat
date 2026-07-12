@echo off
setlocal enabledelayedexpansion

REM Personal AI Runtime — Windows dependency installer
REM Usage: install.bat

echo.
echo === Personal AI Runtime — Windows Install ===
echo.

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  set PY_CMD=py -3.12
  goto :found_python
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  set PY_CMD=python
  goto :found_python
)

echo [ERROR] Python 3.12+ not found. Install from https://www.python.org/downloads/
exit /b 1

:found_python
echo Using: %PY_CMD%
%PY_CMD% --version || exit /b 1

echo.
echo [1/3] Installing backend dependencies...
pushd backend
%PY_CMD% scripts\check_dependency_sync.py
if %ERRORLEVEL% neq 0 (
  popd
  exit /b 1
)
%PY_CMD% -m pip install --require-hashes -r requirements.lock
if %ERRORLEVEL% neq 0 (
  popd
  exit /b 1
)
popd

echo.
echo [2/3] Installing frontend dependencies...
pushd frontend
call npm ci --no-audit --no-fund
if %ERRORLEVEL% neq 0 (
  popd
  exit /b 1
)
popd

echo.
echo [3/3] Installing desktop dependencies...
pushd desktop
call npm ci --no-audit --no-fund
if %ERRORLEVEL% neq 0 (
  popd
  exit /b 1
)
popd

echo.
echo === Install complete ===
echo.
echo Next steps:
echo   make dev          (or use Makefile.ps1)
echo   make desktop      Desktop app
echo   See README.md     Full guide
echo.

endlocal
