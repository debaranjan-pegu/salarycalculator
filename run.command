#!/bin/bash
# Start the Salary Calculator on this computer only (macOS).
cd "$(dirname "$0")" || exit 1
exec ./setup.sh run
