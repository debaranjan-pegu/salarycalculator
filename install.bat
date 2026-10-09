@echo off
REM Install the Salary Calculator so it starts automatically when you sign in (Windows).
setlocal
cd /d "%~dp0"
set "APPDIR=%CD%"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python 3 was not found.
  echo Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run this again.
  echo.
  pause
  exit /b 1
)

set "SHARE="
set /p SHARE=Share with your team over the network? [y/N] 
set "MODE="
if /i "%SHARE%"=="y" set "MODE=--network"

REM a hidden launcher, so no console window appears at start-up
> "%APPDIR%\salarycalc-run.vbs" (
  echo Set sh = CreateObject("WScript.Shell"^)
  echo sh.CurrentDirectory = "%APPDIR%"
  echo sh.Run """pythonw"" ""%APPDIR%\app.py"" --no-browser %MODE%", 0, False
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LNK=%STARTUP%\Salary Calculator.lnk"
if not exist "%STARTUP%" mkdir "%STARTUP%"

> "%TEMP%\salarycalc-lnk.vbs" (
  echo Set sh = CreateObject("WScript.Shell"^)
  echo Set lnk = sh.CreateShortcut("%LNK%"^)
  echo lnk.TargetPath = "%APPDIR%\salarycalc-run.vbs"
  echo lnk.WorkingDirectory = "%APPDIR%"
  echo lnk.Description = "Salary Calculator"
  echo lnk.Save
)
cscript //nologo "%TEMP%\salarycalc-lnk.vbs" >nul
del "%TEMP%\salarycalc-lnk.vbs" >nul 2>nul

REM start it right now too
start "" wscript "%APPDIR%\salarycalc-run.vbs"

echo.
echo Installed. It will start automatically when you sign in to Windows.
echo Open it at  http://127.0.0.1:8765/
echo Remove it later by running uninstall.bat
echo.
pause
