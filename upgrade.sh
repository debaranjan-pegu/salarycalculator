#!/bin/bash
# Update the Salary Calculator to the latest version (Linux).
cd "$(dirname "$0")" || exit 1
exec ./setup.sh upgrade
