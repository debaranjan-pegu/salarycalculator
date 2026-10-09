#!/bin/bash
# Build a self-contained Windows bundle — runs with NO Python installed.
#
#   ./build_windows_bundle.sh [python-version]
#
# Produces dist/SalaryCalculator-Windows-x64.zip. Attach that ZIP to a GitHub
# Release; it is deliberately NOT committed (it is ~11 MB of binary blob).
set -euo pipefail
cd "$(dirname "$0")"

PYVER="${1:-3.12.7}"
ARCH="amd64"
NAME="SalaryCalculator-Windows"
OUT="dist"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "• downloading Python $PYVER (embeddable, $ARCH)…"
curl -fsSL -o "$WORK/py.zip" \
  "https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-$ARCH.zip"

echo "• assembling $NAME/"
rm -rf "$OUT/$NAME"
mkdir -p "$OUT/$NAME/python"
unzip -q "$WORK/py.zip" -d "$OUT/$NAME/python"

# The embedded interpreter takes sys.path solely from this file and, being
# isolated, never prepends the script's own folder — so `python app.py` from the
# bundle root could not import db, calc, report or xlsx. Add the bundle root
# (`..` resolved against python/) to make those importable.
PTH_FILE="$(ls "$OUT/$NAME/python"/*._pth)"
printf '..\n' >> "$PTH_FILE"

for f in app.py auth.py calc.py certgen.py db.py report.py xlsx.py VERSION LICENSE README.md; do
  cp "$f" "$OUT/$NAME/"
done
cp -R seed static "$OUT/$NAME/"

cat > "$OUT/$NAME/Salary Calculator.cmd" <<'EOF'
@echo off
title Salary Calculator
cd /d "%~dp0"
echo Starting the Salary Calculator - keep this window open while you use it.
echo.
python\python.exe app.py
echo.
echo The app has stopped.
pause
EOF

cat > "$OUT/$NAME/Share with team.cmd" <<'EOF'
@echo off
title Salary Calculator (shared)
cd /d "%~dp0"
echo Starting in network mode. Share the https:// address below with your team.
echo Keep this window open while they use it.
echo.
python\python.exe app.py --network
echo.
echo The app has stopped.
pause
EOF

cat > "$OUT/$NAME/Update.cmd" <<'EOF'
@echo off
REM Fetch the newest release and set it up beside this folder, keeping your data.
setlocal
title Update the Salary Calculator
cd /d "%~dp0"
set "HERE=%CD%"
for %%I in ("%HERE%\..") do set "PARENT=%%~fI"
set "REPO=debaranjan-pegu/salarycalculator"

where curl >nul 2>nul || goto :notools
where tar  >nul 2>nul || goto :notools

for /f "usebackq delims=" %%v in ("%HERE%\VERSION") do set "CURRENT=%%v"
if not defined CURRENT goto :damaged
echo This copy is version %CURRENT%.
echo Asking GitHub for the latest release...

REM The Releases API is generated per request. The raw VERSION file is served
REM with cache-control: max-age=300, so right after a release it can still
REM report the previous version - which looks like "nothing happened".
set "LATEST="
curl -fsSL -o "%TEMP%\salarycalc-latest.json" "https://api.github.com/repos/%REPO%/releases/latest"
if errorlevel 1 goto :tryraw
for /f "tokens=2 delims=:," %%a in ('findstr /i tag_name "%TEMP%\salarycalc-latest.json"') do set "RAW=%%a"
if not defined RAW goto :tryraw
set LATEST=%RAW: =%
set LATEST=%LATEST:"=%
set LATEST=%LATEST:v=%
goto :havever

:tryraw
curl -fsSL -o "%TEMP%\salarycalc-version.txt" "https://raw.githubusercontent.com/%REPO%/main/VERSION"
if errorlevel 1 goto :offline
for /f "usebackq delims=" %%v in ("%TEMP%\salarycalc-version.txt") do set "LATEST=%%v"

:havever
if not defined LATEST goto :offline
echo The latest release is %LATEST%.
if /i "%CURRENT%"=="%LATEST%" goto :current

set "TARGET=%PARENT%\SalaryCalculator-Windows-%LATEST%"
if exist "%TARGET%" (
  echo.
  echo Version %LATEST% is already unpacked at:
  echo    %TARGET%
  echo Close this app's window and open that folder instead.
  echo.
  pause
  exit /b 0
)

set "ZIP=%TEMP%\SalaryCalculator-Windows-%LATEST%.zip"
set "STAGE=%TEMP%\salarycalc-stage-%LATEST%"
echo Downloading version %LATEST% ...
curl -fsSL -o "%ZIP%" "https://github.com/%REPO%/releases/download/v%LATEST%/SalaryCalculator-Windows-x64.zip"
if errorlevel 1 goto :nodownload

echo Unpacking ...
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"
tar -xf "%ZIP%" -C "%STAGE%"
if errorlevel 1 goto :nountar
if not exist "%STAGE%\SalaryCalculator-Windows\VERSION" goto :nountar

echo Carrying your records across ...
if exist "%HERE%\salary.db" (
  copy /y "%HERE%\salary.db" "%STAGE%\SalaryCalculator-Windows\salary.db" >nul 2>&1
  if not exist "%STAGE%\SalaryCalculator-Windows\salary.db" goto :nodata
)
if exist "%HERE%\certs" xcopy /e /i /y "%HERE%\certs" "%STAGE%\SalaryCalculator-Windows\certs" >nul 2>&1

move "%STAGE%\SalaryCalculator-Windows" "%TARGET%" >nul
if errorlevel 1 goto :nomove

echo.
echo ================================================================
echo   Version %LATEST% is ready. YOUR CURRENT APP IS STILL %CURRENT%.
echo ================================================================
echo.
echo   1. Close THIS window  - that stops the app you are running now.
echo   2. In the folder that just opened, double-click
echo      "Salary Calculator.cmd" to start %LATEST%.
echo.
echo Your records came across unchanged. The old folder can be deleted.
echo.
start "" explorer "%TARGET%"
pause
exit /b 0

:current
echo.
echo You already have the latest release (%LATEST%). Nothing to do.
echo.
echo (If a release was published in the last few minutes, run Update.cmd
echo again in a moment.)
echo.
pause
exit /b 0

:nodata
echo.
echo Your salary.db could not be copied into the new version, so nothing was
echo changed - this folder is still your live copy. Run Update.cmd again, or
echo copy salary.db across by hand from:
echo    %HERE%
echo to:
echo    %STAGE%\SalaryCalculator-Windows
echo.
pause
exit /b 1

:notools
echo.
echo This needs "curl" and "tar", which Windows 10 version 1803 and newer
echo already include. Download the latest version by hand instead:
echo    https://github.com/%REPO%/releases
echo Unpack it and copy your salary.db into the new folder.
echo.
pause
exit /b 1

:damaged
echo.
echo This folder has no readable VERSION file, so it is not a complete copy.
echo Download the latest version by hand:
echo    https://github.com/%REPO%/releases
echo.
pause
exit /b 1

:offline
echo.
echo Could not reach GitHub. Check your internet connection and try again.
echo.
pause
exit /b 1

:nodownload
echo.
echo GitHub did not have version %LATEST% ready to download. Try again in a
echo few minutes, or get it by hand from:
echo    https://github.com/%REPO%/releases
echo.
pause
exit /b 1

:nountar
echo.
echo The download could not be unpacked - it may have been incomplete.
echo Delete this file and run Update.cmd again:
echo    %ZIP%
echo.
pause
exit /b 1

:nomove
echo.
echo The new version was unpacked to:
echo    %STAGE%\SalaryCalculator-Windows
echo but it could not be moved next to this folder. Close this app's window
echo and run Update.cmd again.
echo.
pause
exit /b 1
EOF

# Windows wants CRLF in a .cmd, and Notepad shows an LF-only file as one long
# line. awk keeps this portable across the Mac and the CI runner.
for f in "$OUT/$NAME"/*.cmd; do
  awk 'BEGIN{ORS="\r\n"} { sub(/\r$/, ""); print }' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
done

cat > "$OUT/$NAME/README-WINDOWS.txt" <<'EOF'
Salary Calculator - portable Windows edition
============================================

Nothing to install. This folder already contains its own copy of Python.

TO USE IT
  Double-click  "Salary Calculator.cmd"
  Your browser opens at http://127.0.0.1:8765/

TO SHARE IT WITH YOUR TEAM
  Double-click  "Share with team.cmd"
  It prints an https:// address like  https://192.168.1.24:8765/
  Give that address to your colleagues; they just open it in a browser.
  Create an account for each person under  Users & Access.

YOUR DATA
  Everything is stored in  salary.db  in this same folder.
  To move or back it up, copy that one file (or the whole folder).

FIRST RUN
  You will be asked to create the administrator account and shown a
  one-time recovery code - keep it somewhere safe.

TO UPGRADE
  Double-click  "Update.cmd"
  It downloads the newest version into a folder beside this one and copies
  your salary.db across. Then close this app's window and open the new folder.
  Nothing to install, and no administrator rights are involved.
  If that ever fails, do it by hand: download the newer version, unpack it,
  and copy your salary.db into it.
EOF

echo "• zipping…"
( cd "$OUT" && rm -f "$NAME-x64.zip" && zip -qr "$NAME-x64.zip" "$NAME" )

SIZE=$(du -h "$OUT/$NAME-x64.zip" | cut -f1)
echo "• done: $OUT/$NAME-x64.zip  ($SIZE)"
