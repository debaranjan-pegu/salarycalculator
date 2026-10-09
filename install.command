#!/bin/bash
# Install the Salary Calculator so it starts automatically every time you log in.
# Double-click this file (macOS).
cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"
PY="$(command -v python3)"
LABEL="com.salarycalculator.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ -z "$PY" ]; then
  echo "Python 3 was not found."
  echo "Install it from https://www.python.org/downloads/ and run this again."
  read -n 1 -s -r -p "Press any key to close…"
  exit 1
fi

read -r -p "Share with your team over the network? [y/N] " SHARE
ARGS="    <string>$PY</string>
    <string>$APP_DIR/app.py</string>
    <string>--no-browser</string>"
case "$SHARE" in
  y|Y) ARGS="$ARGS
    <string>--network</string>" ;;
esac

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
$ARGS
  </array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$APP_DIR/server.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/server.log</string>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" >/dev/null 2>&1
launchctl load "$PLIST"

echo
echo "Installed. It will start automatically every time you log in."
echo "Open it at  http://127.0.0.1:8765/"
echo "Remove it later with:  ./uninstall.command"
read -n 1 -s -r -p "Press any key to close…"
