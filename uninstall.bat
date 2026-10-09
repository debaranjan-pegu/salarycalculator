@echo off
REM Remove the automatic start-up for the Salary Calculator (Windows).
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
del "%STARTUP%\Salary Calculator.lnk" >nul 2>nul
del "%~dp0salarycalc-run.vbs" >nul 2>nul
echo Auto-start removed. Your data and the app itself are untouched.
pause
