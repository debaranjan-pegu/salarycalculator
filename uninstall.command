#!/bin/bash
# Remove the automatic start-up for the Salary Calculator (macOS).
PLIST="$HOME/Library/LaunchAgents/com.salarycalculator.server.plist"
launchctl unload "$PLIST" >/dev/null 2>&1
rm -f "$PLIST"
echo "Auto-start removed. Your data and the app itself are untouched."
read -n 1 -s -r -p "Press any key to close…"
