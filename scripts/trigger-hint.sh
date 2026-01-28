#!/bin/bash
#
# Manually trigger a hint request (for testing without controller hotkeys)
#
# Usage: ./trigger-hint.sh [request|view]
#

HINTS_DIR="/userdata/system/ai-hints"

case "${1:-request}" in
    request)
        echo "Triggering hint request..."
        touch "$HINTS_DIR/.request_hint"
        echo "Done. Watch for 'Hint Ready!' notification."
        ;;
    view)
        echo "Triggering hint view..."
        touch "$HINTS_DIR/.view_hint"
        echo "Done."
        ;;
    *)
        echo "Usage: $0 [request|view]"
        exit 1
        ;;
esac
