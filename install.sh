#!/bin/bash
# Make the Salary Calculator start automatically at login (Linux).
cd "$(dirname "$0")" || exit 1
exec ./setup.sh install
