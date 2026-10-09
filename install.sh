#!/bin/bash
# Install the Salary Calculator so it starts automatically at login (Linux, systemd --user).
cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"
PY="$(command -v python3)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/salarycalc.service"

if [ -z "$PY" ]; then
  echo "Python 3 was not found. Install it with your package manager, e.g. sudo apt install python3"
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd was not found on this system."
  echo "Start the app manually with ./run.sh instead."
  exit 1
fi

read -r -p "Share with your team over the network? [y/N] " SHARE
EXTRA=""
case "$SHARE" in y|Y) EXTRA="--network" ;; esac

mkdir -p "$UNIT_DIR"
cat > "$UNIT" <<UNITEOF
[Unit]
Description=Salary Calculator (offline salary breakup tool)

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$PY $APP_DIR/app.py --no-browser $EXTRA
Restart=on-failure

[Install]
WantedBy=default.target
UNITEOF

systemctl --user daemon-reload
systemctl --user enable --now salarycalc.service

echo
echo "Installed and running. It will start automatically at login."
echo "Open it at  http://127.0.0.1:8765/"
echo "Remove it later with:  ./uninstall.sh"
