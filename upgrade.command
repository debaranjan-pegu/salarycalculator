#!/bin/bash
# Update the Salary Calculator to the latest version (macOS).
cd "$(dirname "$0")" || exit 1
./setup.sh upgrade
read -n 1 -s -r -p "Press any key to close…"
