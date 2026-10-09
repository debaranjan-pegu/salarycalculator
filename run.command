#!/bin/bash
# Double-click launcher for the Salary Calculator (macOS).
# Starts the local server and opens your browser. Close this window to stop.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required but was not found."
  echo "Install it from https://www.python.org/downloads/ and try again."
  read -n 1 -s -r -p "Press any key to close…"
  exit 1
fi

exec python3 app.py "$@"
