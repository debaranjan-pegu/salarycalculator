#!/bin/bash
# Make the Salary Calculator start automatically at login (macOS).
cd "$(dirname "$0")" || exit 1
./setup.sh install
read -n 1 -s -r -p "Press any key to close…"
