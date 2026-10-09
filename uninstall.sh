#!/bin/bash
# Stop the Salary Calculator starting automatically (Linux).
cd "$(dirname "$0")" || exit 1
exec ./setup.sh uninstall
