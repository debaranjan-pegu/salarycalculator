@echo off
REM Salary Calculator - one setup script for Windows.
REM
REM   setup.bat run        start it now (this computer only)
REM   setup.bat share      start it and share with your team
REM   setup.bat install    start automatically every time you sign in
REM   setup.bat uninstall  stop starting automatically
REM   setup.bat upgrade    update to the latest version
REM
REM It installs Python 3 for you if the machine does not have it.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "APPDIR=%CD%"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=run"
set "PYEXE="
set "PYWN="

call :find_python
if not defined PYEXE (
  call :install_python
  call :find_python
)
if not defined PYEXE (
  echo.
  echo Python 3 could not be installed automatically.
  echo Please install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run this again.
  echo.
  pause
  exit /b 1
)
call :windowexe

if /i "%MODE%"=="run"       goto :do_run
if /i "%MODE%"=="share"     goto :do_share
if /i "%MODE%"=="install"   goto :do_install
if /i "%MODE%"=="uninstall" goto :do_uninstall
if /i "%MODE%"=="upgrade"   goto :do_upgrade
echo Usage: setup.bat [run^|share^|install^|uninstall^|upgrade]
pause
exit /b 0

REM ---------------------------------------------------------------- helpers

:find_python
set "PYEXE="
python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE (
  py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
  if not errorlevel 1 set "PYEXE=py"
)
if not defined PYEXE (
  for %%V in (313 312 311 310 39) do (
    if not defined PYEXE (
      if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    )
  )
)
goto :eof

:install_python
echo Python 3 was not found - downloading it from python.org (about 25 MB)...
set "ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $v='3.12.7'; $a='%ARCH%'; $u=\"https://www.python.org/ftp/python/$v/python-$v-$a.exe\"; $o=Join-Path $env:TEMP 'salarycalc-python.exe'; Invoke-WebRequest -Uri $u -OutFile $o; Start-Process -FilePath $o -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=1' -Wait" 
if errorlevel 1 echo Automatic installation did not complete.
goto :eof

:windowexe
set "PYWN=%PYEXE%"
if /i "%PYEXE%"=="python" set "PYWN=pythonw"
if /i "%PYEXE%"=="py" set "PYWN=pyw"
goto :eof

:startup_shortcut
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
goto :eof

REM ---------------------------------------------------------------- modes

:do_run
"%PYEXE%" "%APPDIR%\app.py"
pause
exit /b 0

:do_share
echo Starting in network mode (HTTPS). Keep this window open while your team uses it.
echo.
"%PYEXE%" "%APPDIR%\app.py" --network
pause
exit /b 0

:do_install
set "SHARE="
set /p SHARE=Share with your team over the network? [y/N] 
set "NET="
if /i "%SHARE%"=="y" set "NET=--network"

> "%APPDIR%\salarycalc-run.vbs" (
  echo Set sh = CreateObject("WScript.Shell"^)
  echo sh.CurrentDirectory = "%APPDIR%"
  echo sh.Run """%PYWN%"" ""%APPDIR%\app.py"" --no-browser %NET%", 0, False
)
call :startup_shortcut
start "" wscript "%APPDIR%\salarycalc-run.vbs"

echo.
echo Installed. It will start automatically when you sign in to Windows.
echo Open it at  http://127.0.0.1:8765/
echo Remove it later by running:  setup.bat uninstall
echo.
pause
exit /b 0

:do_uninstall
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
del "%STARTUP%\Salary Calculator.lnk" >nul 2>nul
del "%APPDIR%\salarycalc-run.vbs" >nul 2>nul
echo Auto-start removed. Your data and the app itself are untouched.
pause
exit /b 0

:do_upgrade
where git >nul 2>nul
if errorlevel 1 (
  echo git was not found, so this copy cannot update itself.
  echo Download the latest version and replace these files.
  pause
  exit /b 0
)
if not exist "%APPDIR%\.git" (
  echo This copy is not a git checkout, so it cannot update itself.
  echo Download the latest version and replace these files.
  pause
  exit /b 0
)
echo Updating from GitHub...
git -C "%APPDIR%" pull --ff-only
echo.
echo Updated. If the app was already running, close it and start it again.
pause
exit /b 0
