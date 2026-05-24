#!/bin/bash
# ==============================================================================
#  STREAM DECK SERVICE STOPPER
# ==============================================================================

echo "============================================================"
echo "          STOPPING STREAM DECK SYSTEMD SERVICE"
echo "============================================================"

# Stop the service
echo "[INFO] Stopping streamdeck.service..."
sudo systemctl stop streamdeck.service

# Disable the service
echo "[INFO] Disabling streamdeck.service..."
sudo systemctl disable streamdeck.service

echo "[INFO] Service stopped and disabled successfully!"
echo "============================================================"
