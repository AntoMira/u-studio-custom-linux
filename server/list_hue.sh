#!/bin/bash
# ==============================================================================
#  PHILIPS HUE DEVICE LISTER LAUNCHER
# ==============================================================================

# Get the absolute path to the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if Python virtual environment exists
if [ -d "$SCRIPT_DIR/venv" ]; then
    # Activate virtual environment
    source "$SCRIPT_DIR/venv/bin/activate"
else
    echo "[WARNING] Virtual environment 'venv' not found. Running with system python..."
fi

# Run the python lister script, forwarding all parameters passed to this shell script
python3 "$SCRIPT_DIR/list_hue.py" "$@"
