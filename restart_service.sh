#!/bin/bash
# ==============================================================================
#  STREAM DECK SERVICE RESTARTER
# ==============================================================================

echo "============================================================"
echo "          RESTARTING STREAM DECK SYSTEMD SERVICE"
echo "============================================================"

# Restart the service
echo "[INFO] Restarting streamdeck.service..."
sudo systemctl restart streamdeck.service

echo "[INFO] Service restarted successfully!"
echo "============================================================"
