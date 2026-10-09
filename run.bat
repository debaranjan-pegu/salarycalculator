@echo off
REM Double-click launcher for the Salary Calculator (Windows).
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python 3 is required but was not found.
  echo Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

python app.py %*
pause
