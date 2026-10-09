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
  Download the newer version of this folder and copy your salary.db into it.
EOF

echo "• zipping…"
( cd "$OUT" && rm -f "$NAME-x64.zip" && zip -qr "$NAME-x64.zip" "$NAME" )

SIZE=$(du -h "$OUT/$NAME-x64.zip" | cut -f1)
echo "• done: $OUT/$NAME-x64.zip  ($SIZE)"
