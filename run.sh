#!/bin/bash
# Launcher for the Salary Calculator on Linux.
# Make it executable once:  chmod +x run.sh   then:  ./run.sh
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required but was not found."
  echo "Install it with your package manager, e.g.  sudo apt install python3"
  exit 1
fi

exec python3 app.py "$@"
