#!/bin/bash
#
# Securely set up API key for AI Hint System
# This stores the key in a separate .secrets file with restricted permissions
#

SECRETS_FILE="/userdata/system/ai-hints/.secrets"

echo "========================================"
echo "  AI Hint System - API Key Setup"
echo "========================================"
echo
echo "This will store your API key securely in:"
echo "  $SECRETS_FILE"
echo
echo "The key will NOT be stored in config.json"
echo

# Prompt for key (input hidden)
echo -n "Paste your API key (input hidden): "
read -s API_KEY
echo
echo

if [ -z "$API_KEY" ]; then
    echo "Error: No API key entered."
    exit 1
fi

# Create secrets file with restricted permissions
mkdir -p "$(dirname "$SECRETS_FILE")"
touch "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"

# Write key
cat > "$SECRETS_FILE" << EOF
# AI Hint System API Key
# This file has restricted permissions (600)
# Do not share or commit this file
API_KEY=$API_KEY
EOF

chmod 600 "$SECRETS_FILE"

echo "API key saved securely!"
echo
echo "File permissions: $(ls -la "$SECRETS_FILE" | awk '{print $1}')"
echo
echo "Now restart the service:"
echo "  batocera-services restart ai_hint"
echo
