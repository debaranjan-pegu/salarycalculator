#!/bin/bash
# Share the Salary Calculator with your team (Linux).
# Run this on the ONE computer that will host it:  ./share.sh
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it with your package manager, e.g. sudo apt install python3"
  exit 1
fi

echo "Starting in network mode (HTTPS). Keep this running while your team uses it."
echo
exec python3 app.py --network "$@"
