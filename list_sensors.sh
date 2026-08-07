#!/bin/bash
# Convenient wrapper to run list_sensors.py using server virtual environment

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$BASE_DIR/server/venv/bin/python3"

if [ -f "$VENV_PYTHON" ]; then
    "$VENV_PYTHON" "$BASE_DIR/server/list_sensors.py" "$@"
else
    python3 "$BASE_DIR/server/list_sensors.py" "$@"
fi
