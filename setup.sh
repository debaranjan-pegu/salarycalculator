#!/bin/bash
# Salary Calculator — one setup script for macOS and Linux.
#
#   ./setup.sh run        start it now (this computer only)
#   ./setup.sh share      start it and share with your team
#   ./setup.sh install    start automatically every time you log in
#   ./setup.sh uninstall  stop starting automatically
#   ./setup.sh upgrade    update to the latest version
#
# It installs Python 3 for you if the machine does not have it.
set -u
cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"
MODE="${1:-run}"

LABEL="com.salarycalculator.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UNIT="$HOME/.config/systemd/user/salarycalc.service"

say()  { printf "%s\n" "$*"; }
die()  { printf "\n%s\n" "$*"; printf "Press Enter to close… "; read -r _ 2>/dev/null || true; exit 1; }
is_mac() { [ "$(uname)" = "Darwin" ]; }
have() { command -v "$1" >/dev/null 2>&1; }

# ------------------------------------------------------------------ Python 3

find_python() {
  local c
  for c in python3 python; do
    if have "$c" && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

install_python() {
  say "Python 3 was not found — trying to install it for you automatically…"
  if is_mac; then
    if have brew; then
      say "Using Homebrew…"
      brew install python && return 0
    fi
    say "Asking macOS to install the Apple command line tools (they include Python 3)."
    xcode-select --install >/dev/null 2>&1 || true
    say ""
    say "A window has opened. Finish that installation, then run this again."
    return 1
  fi
  if have apt-get;  then sudo apt-get update && sudo apt-get install -y python3 && return 0; fi
  if have dnf;      then sudo dnf install -y python3 && return 0; fi
  if have yum;      then sudo yum install -y python3 && return 0; fi
  if have pacman;   then sudo pacman -Sy --noconfirm python && return 0; fi
  if have zypper;   then sudo zypper --non-interactive install python3 && return 0; fi
  if have apk;      then sudo apk add python3 && return 0; fi
  say "No known package manager found. Please install Python 3, then run this again."
  return 1
}

ensure_python() {
  local py
  if py="$(find_python)"; then PY="$py"; return 0; fi
  install_python || true
  if py="$(find_python)"; then PY="$py"; return 0; fi
  die "Python 3 is still not available. Install it from https://www.python.org/downloads/ and run this again."
}

# ------------------------------------------------------------------ auto start

write_plist() {
  local share="$1" extra=""
  [ "$share" = "1" ] && extra="    <string>--network</string>"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$APP_DIR/app.py</string>
    <string>--no-browser</string>
$extra
  </array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$APP_DIR/server.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/server.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST" >/dev/null 2>&1 || true
  launchctl load "$PLIST"
}

write_unit() {
  local share="$1" extra=""
  [ "$share" = "1" ] && extra="--network"
  mkdir -p "$(dirname "$UNIT")"
  cat > "$UNIT" <<EOF
[Unit]
Description=Salary Calculator (offline salary breakup tool)

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$PY $APP_DIR/app.py --no-browser $extra
Restart=on-failure

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now salarycalc.service
}

ask_share() {
  printf "Share with your team over the network? [y/N] "
  read -r answer 2>/dev/null || answer=""
  case "$answer" in y|Y) echo 1 ;; *) echo 0 ;; esac
}

restart_service() {
  if is_mac && [ -f "$PLIST" ]; then
    launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  elif [ -f "$UNIT" ] && have systemctl; then
    systemctl --user restart salarycalc.service >/dev/null 2>&1 || true
  fi
}

# ------------------------------------------------------------------ go

ensure_python

case "$MODE" in
  run)
    exec "$PY" "$APP_DIR/app.py"
    ;;
  share)
    say "Starting in network mode (HTTPS). Keep this window open while your team uses it."
    say ""
    exec "$PY" "$APP_DIR/app.py" --network
    ;;
  install)
    S="$(ask_share)"
    if is_mac; then write_plist "$S"; else write_unit "$S"; fi
    say ""
    say "Installed. It will start automatically every time you log in."
    say "Open it at  http://127.0.0.1:8765/"
    say "Remove it later with:  ./setup.sh uninstall"
    ;;
  uninstall)
    if is_mac; then
      launchctl unload "$PLIST" >/dev/null 2>&1 || true
      rm -f "$PLIST"
    else
      have systemctl && systemctl --user disable --now salarycalc.service >/dev/null 2>&1 || true
      have systemctl && systemctl --user daemon-reload >/dev/null 2>&1 || true
      rm -f "$UNIT"
    fi
    say "Auto-start removed. Your data and the app itself are untouched."
    ;;
  upgrade)
    if [ -d "$APP_DIR/.git" ]; then
      say "Updating from GitHub…"
      git -C "$APP_DIR" pull --ff-only
      restart_service
      say ""
      say "Updated. If the app was already running, close it and start it again."
    else
      say "This copy is not a git checkout, so it cannot update itself."
      say "Download the latest version from the project page and replace these files."
    fi
    ;;
  *)
    say "Usage: ./setup.sh [run|share|install|uninstall|upgrade]"
    ;;
esac
