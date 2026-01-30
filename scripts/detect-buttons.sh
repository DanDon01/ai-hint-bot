#!/bin/bash
#
# Detect controller button codes
# Run on Batocera to find correct button names for config.json
#

CONTROLLER="${1:-/dev/input/event24}"

echo "========================================"
echo "  Controller Button Detector"
echo "========================================"
echo
echo "Controller: $CONTROLLER"
echo
echo "Press buttons on your controller."
echo "Press Ctrl+C to stop."
echo
echo "Look for buttons like Select, L1, R1"
echo "========================================"
echo

python3 /userdata/system/ai-hints/detect-buttons.py "$CONTROLLER"
