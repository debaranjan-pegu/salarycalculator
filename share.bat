@echo off
REM Share the Salary Calculator with your team (Windows).
REM Double-click this on the ONE computer that will host it.
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

echo Starting in network mode (HTTPS). Keep this window open while your team uses it.
echo.
python app.py --network %*
pause
