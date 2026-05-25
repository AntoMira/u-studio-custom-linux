#!/bin/bash
# ==============================================================================
#  STREAM DECK SERVICE INSTALLER & STARTER
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="streamdeck.service"
TARGET_DIR="/etc/systemd/system"

echo "============================================================"
echo "          INSTALLING STREAM DECK SYSTEMD SERVICE"
echo "============================================================"

# Check if service file exists in server directory
if [ ! -f "$SCRIPT_DIR/server/$SERVICE_FILE" ]; then
    echo "[-] Error: $SERVICE_FILE not found in $SCRIPT_DIR/server"
    exit 1
fi

# Stop any running systemd service first to cleanly restart
if systemctl is-active --quiet streamdeck.service; then
    echo "[INFO] Stopping existing streamdeck.service..."
    sudo systemctl stop streamdeck.service
fi

# Copy service file to systemd directory using sudo
echo "[INFO] Copying service configuration to $TARGET_DIR..."
sudo cp "$SCRIPT_DIR/server/$SERVICE_FILE" "$TARGET_DIR/$SERVICE_FILE"

# Reload systemd configuration
echo "[INFO] Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable service to start on boot
echo "[INFO] Enabling streamdeck.service on system boot..."
sudo systemctl enable streamdeck.service

# Start the service
echo "[INFO] Starting streamdeck.service..."
sudo systemctl start streamdeck.service

echo "[INFO] Service installation and startup complete!"
echo "------------------------------------------------------------"
sudo systemctl status streamdeck.service --no-pager
echo "============================================================"
