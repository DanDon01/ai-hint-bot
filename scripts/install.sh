#!/bin/bash
#
# AI Hint System Installer for Batocera
#
# Run this script on your Batocera system after copying files:
#   chmod +x install.sh && ./install.sh
#

set -e

INSTALL_DIR="/userdata/system/ai-hints"
SERVICE_DIR="/userdata/system/services"

echo "========================================"
echo "  AI Hint System Installer"
echo "========================================"
echo

# Check if running on Batocera
if [ ! -d "/userdata" ]; then
    echo "ERROR: This doesn't appear to be a Batocera system."
    echo "       /userdata directory not found."
    exit 1
fi

# Create directories
echo "[1/5] Creating directories..."
mkdir -p "$INSTALL_DIR/archive"
mkdir -p "$SERVICE_DIR"

# Check for daemon.py in current directory or parent
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DAEMON_SRC=""
CONFIG_SRC=""
SERVICE_SRC=""

for dir in "$SCRIPT_DIR" "$SCRIPT_DIR/.." "$SCRIPT_DIR/../src"; do
    if [ -f "$dir/daemon.py" ]; then
        DAEMON_SRC="$dir/daemon.py"
    fi
    if [ -f "$dir/config.json" ]; then
        CONFIG_SRC="$dir/config.json"
    fi
done

for dir in "$SCRIPT_DIR" "$SCRIPT_DIR/.." "$SCRIPT_DIR/../service"; do
    if [ -f "$dir/ai_hint" ]; then
        SERVICE_SRC="$dir/ai_hint"
    fi
done

# Copy daemon
echo "[2/5] Installing daemon..."
if [ -n "$DAEMON_SRC" ]; then
    cp "$DAEMON_SRC" "$INSTALL_DIR/daemon.py"
    chmod +x "$INSTALL_DIR/daemon.py"
    echo "       Copied from $DAEMON_SRC"
else
    echo "       WARNING: daemon.py not found in script directory"
    echo "       Please copy daemon.py to $INSTALL_DIR/daemon.py manually"
fi

# Copy config (don't overwrite existing)
echo "[3/5] Setting up config..."
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    if [ -n "$CONFIG_SRC" ]; then
        cp "$CONFIG_SRC" "$INSTALL_DIR/config.json"
        echo "       Created default config"
    else
        echo "       WARNING: config.json template not found"
    fi
else
    echo "       Config already exists, not overwriting"
fi

# Install service
echo "[4/5] Installing service..."
if [ -n "$SERVICE_SRC" ]; then
    cp "$SERVICE_SRC" "$SERVICE_DIR/ai_hint"
    chmod +x "$SERVICE_DIR/ai_hint"
    # Ensure UNIX line endings
    sed -i 's/\r$//' "$SERVICE_DIR/ai_hint"
    echo "       Service installed"
else
    echo "       WARNING: ai_hint service script not found"
fi

# Enable RetroArch network commands
echo "[5/5] Configuring RetroArch..."
BATOCERA_CONF="/userdata/system/batocera.conf"
if ! grep -q "global.retroarch.network_cmd_enable=true" "$BATOCERA_CONF" 2>/dev/null; then
    echo "global.retroarch.network_cmd_enable=true" >> "$BATOCERA_CONF"
    echo "global.retroarch.network_cmd_port=55355" >> "$BATOCERA_CONF"
    echo "       Network commands enabled in batocera.conf"
else
    echo "       Network commands already enabled"
fi

echo
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/config.json"
echo "     - Add your API key (api_key field)"
echo "     - Adjust controller_device if needed"
echo
echo "  2. Reboot or start the service:"
echo "     batocera-services start ai_hint"
echo
echo "  3. Test with a game:"
echo "     - Press Select+L1 to request a hint"
echo "     - Press Select+R1 to view the hint"
echo
echo "Log file: $INSTALL_DIR/daemon.log"
echo
