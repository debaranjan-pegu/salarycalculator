#!/bin/bash
# Remove the automatic start-up for the Salary Calculator (Linux).
UNIT="$HOME/.config/systemd/user/salarycalc.service"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now salarycalc.service >/dev/null 2>&1
  systemctl --user daemon-reload >/dev/null 2>&1
fi
rm -f "$UNIT"
echo "Auto-start removed. Your data and the app itself are untouched."
