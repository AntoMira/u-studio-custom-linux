#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Resolve the absolute directory of this script to handle execution from any folder
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "          STREAM DECK APPLICATION RUNNER"
echo "============================================================"

# 1. Detect/Create Virtual Environment with Python 3.9
if [ ! -d "venv" ]; then
    echo "[INFO] Virtual environment 'venv' not found. Creating with Python 3.9..."
    python3.9 -m venv venv
else
    # Check if the existing virtual environment is using Python 3.9
    VENV_PYTHON_VERSION=$(venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "")
    if [ "$VENV_PYTHON_VERSION" != "3.9" ]; then
        echo "[INFO] Existing virtual environment uses Python $VENV_PYTHON_VERSION. Recreating with Python 3.9..."
        python3.9 -m venv venv --clear
    else
        echo "[INFO] Existing Python 3.9 virtual environment found."
    fi
fi

# 2. Activate Virtual Environment
echo "[INFO] Activating virtual environment..."
source venv/bin/activate

# 3. Verify and install dependencies
if [ -f "requirements.txt" ]; then
    echo "[INFO] Installing/verifying dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "[WARNING] requirements.txt not found. Skipping dependency installation."
fi

# 4. Execute the Application
echo "[INFO] Launching Stream Deck application..."
echo "------------------------------------------------------------"
python main.py
