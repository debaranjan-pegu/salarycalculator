#!/bin/bash
# Share the Salary Calculator with your team (macOS).
# Double-click this on the ONE computer that will host it; everyone else just
# opens the address it prints in their browser. Close this window to stop.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required but was not found."
  echo "Install it from https://www.python.org/downloads/ and try again."
  read -n 1 -s -r -p "Press any key to close…"
  exit 1
fi

echo "Starting in network mode (HTTPS). Keep this window open while your team uses it."
echo
exec python3 app.py --network "$@"
