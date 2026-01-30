#!/bin/bash
#
# Delayed hint trigger - gives you time to walk to the TV
#

DELAY="${1:-10}"
ACTION="${2:-request}"

echo "========================================"
echo "  Delayed Hint Trigger"
echo "========================================"
echo
echo "Action: $ACTION"
echo "Starting in $DELAY seconds..."
echo
echo "Go to your TV now!"
echo

for i in $(seq $DELAY -1 1); do
    echo "  $i..."
    sleep 1
done

echo
echo "Triggering now!"
/userdata/system/ai-hints/trigger-hint.sh "$ACTION"
echo
echo "Done. Check your TV for the notification."
