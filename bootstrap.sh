#!/bin/bash
# One-line install for macOS and Linux:
#
#   curl -fsSL https://raw.githubusercontent.com/debaranjan-pegu/salarycalculator/main/bootstrap.sh | bash
#
# Downloads the app to ~/SalaryCalculator (override with SALARYCALC_DIR) and
# tells you how to start it. Nothing is installed system-wide.
set -e

REPO="${SALARYCALC_REPO:-https://github.com/debaranjan-pegu/salarycalculator.git}"
DEST="${SALARYCALC_DIR:-$HOME/SalaryCalculator}"

command -v git >/dev/null 2>&1 || { echo "git is required but was not found."; exit 1; }
command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 is required. Install it from https://www.python.org/downloads/"; exit 1; }

if [ -d "$DEST/.git" ]; then
  echo "Updating $DEST …"
  git -C "$DEST" pull --ff-only
else
  echo "Downloading to $DEST …"
  git clone --depth 1 "$REPO" "$DEST"
fi

cd "$DEST"
chmod +x ./*.command ./*.sh 2>/dev/null || true

echo
echo "Installed in $DEST"
if [ "$(uname)" = "Darwin" ]; then
  echo "  Start it now        :  open \"$DEST/run.command\""
  echo "  Start automatically :  open \"$DEST/install.command\""
  echo "  Share with the team :  open \"$DEST/share.command\""
else
  echo "  Start it now        :  cd \"$DEST\" && ./run.sh"
  echo "  Start automatically :  cd \"$DEST\" && ./install.sh"
  echo "  Share with the team :  cd \"$DEST\" && ./share.sh"
fi
