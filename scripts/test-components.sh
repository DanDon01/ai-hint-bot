#!/bin/bash
#
# Test individual components of the AI Hint System
#
# Run on Batocera to verify each component works
#

echo "========================================"
echo "  AI Hint System Component Tests"
echo "========================================"
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Counters
CRITICAL_PASS=0
CRITICAL_FAIL=0
OPTIONAL_PASS=0
OPTIONAL_WARN=0

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "       $1"; }
critical() { echo -e "${CYAN}[CRITICAL]${NC}"; }

# Track results
critical_pass() { pass "$1"; ((CRITICAL_PASS++)); }
critical_fail() { fail "$1"; ((CRITICAL_FAIL++)); }
optional_pass() { pass "$1"; ((OPTIONAL_PASS++)); }
optional_warn() { warn "$1"; ((OPTIONAL_WARN++)); }

echo "Legend: ${CYAN}[CRITICAL]${NC} = Must pass | ${YELLOW}[WARN]${NC} = Optional"
echo

# =============================================================================
# Test 1: Python (CRITICAL)
# =============================================================================
echo "--- Test 1: Python Environment --- $(critical)"
if command -v python3 &> /dev/null; then
    VERSION=$(python3 --version 2>&1)
    critical_pass "Python3 found: $VERSION"
else
    critical_fail "Python3 not found"
fi

# Test built-in modules (all critical)
for module in socket json subprocess os threading urllib.request base64; do
    if python3 -c "import $module" 2>/dev/null; then
        critical_pass "Module: $module"
    else
        critical_fail "Module: $module"
    fi
done

# =============================================================================
# Test 2: Optional Modules
# =============================================================================
echo
echo "--- Test 2: Optional Modules --- (Nice to have)"
if python3 -c "import evdev" 2>/dev/null; then
    optional_pass "evdev available (controller hotkeys will work)"
    EVDEV_OK=1
else
    optional_warn "evdev not available (will use file-based triggers instead)"
    EVDEV_OK=0
fi

if python3 -c "from PIL import Image" 2>/dev/null; then
    optional_pass "PIL/Pillow available (full hint rendering)"
    PIL_OK=1
else
    optional_warn "PIL not available (will try ImageMagick fallback)"
    PIL_OK=0
fi

if command -v convert &> /dev/null; then
    optional_pass "ImageMagick available"
else
    if [ "$PIL_OK" = "0" ]; then
        optional_warn "ImageMagick not available (hint rendering limited)"
    else
        optional_warn "ImageMagick not available (PIL will be used instead)"
    fi
fi

# =============================================================================
# Test 3: RetroArch Network Commands (CRITICAL)
# =============================================================================
echo
echo "--- Test 3: RetroArch Network Commands --- $(critical)"
echo "(Note: Start a game for full test)"

# Check config first
if grep -q "network_cmd_enable.*true" /userdata/system/batocera.conf 2>/dev/null; then
    critical_pass "Network commands enabled in batocera.conf"
else
    critical_fail "Network commands NOT enabled in batocera.conf"
    info "Run: echo 'global.retroarch.network_cmd_enable=true' >> /userdata/system/batocera.conf"
fi

# Check if netcat is available
if command -v nc &> /dev/null; then
    critical_pass "netcat (nc) available for sending commands"
else
    critical_fail "netcat not available"
fi

# =============================================================================
# Test 4: Screenshot Directory (CRITICAL)
# =============================================================================
echo
echo "--- Test 4: Screenshot Directory --- $(critical)"
SCREENSHOT_DIR="/userdata/screenshots"
if [ -d "$SCREENSHOT_DIR" ]; then
    critical_pass "Screenshot directory exists: $SCREENSHOT_DIR"
    COUNT=$(find "$SCREENSHOT_DIR" -name "*.png" 2>/dev/null | wc -l)
    info "Contains $COUNT PNG files"
else
    optional_warn "Screenshot directory not found (will be created on first screenshot)"
fi

# =============================================================================
# Test 5: Hints Directory (CRITICAL)
# =============================================================================
echo
echo "--- Test 5: Hints Directory --- $(critical)"
HINTS_DIR="/userdata/system/ai-hints"
if [ -d "$HINTS_DIR" ]; then
    critical_pass "Hints directory exists: $HINTS_DIR"
else
    mkdir -p "$HINTS_DIR"
    critical_pass "Hints directory created: $HINTS_DIR"
fi

if touch "$HINTS_DIR/test_write" 2>/dev/null; then
    rm "$HINTS_DIR/test_write"
    critical_pass "Hints directory is writable"
else
    critical_fail "Cannot write to hints directory"
fi

# =============================================================================
# Test 6: Network Access (CRITICAL)
# =============================================================================
echo
echo "--- Test 6: Network Access (API) --- $(critical)"
if command -v curl &> /dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://api.anthropic.com 2>/dev/null)
    if [ "$HTTP_CODE" = "000" ]; then
        critical_fail "Cannot reach api.anthropic.com (no network?)"
    else
        critical_pass "api.anthropic.com reachable (HTTP $HTTP_CODE)"
    fi
else
    # Try with Python
    if python3 -c "import urllib.request; urllib.request.urlopen('https://api.anthropic.com', timeout=5)" 2>/dev/null; then
        critical_pass "api.anthropic.com reachable"
    else
        critical_fail "Cannot reach api.anthropic.com"
    fi
fi

# =============================================================================
# Test 7: Display Methods (Optional)
# =============================================================================
echo
echo "--- Test 7: Display Methods --- (Optional - has fallback)"
DISPLAY_METHOD="none"

# Check in priority order (same as daemon.py)
if command -v fbv &> /dev/null; then
    optional_pass "fbv available (framebuffer viewer) - PREFERRED"
    DISPLAY_METHOD="fbv"
else
    info "fbv not available"
fi

if command -v mpv &> /dev/null; then
    optional_pass "mpv available (can display images)"
    [ "$DISPLAY_METHOD" = "none" ] && DISPLAY_METHOD="mpv"
else
    info "mpv not available"
fi

if command -v fbi &> /dev/null; then
    optional_pass "fbi available (framebuffer image viewer)"
    [ "$DISPLAY_METHOD" = "none" ] && DISPLAY_METHOD="fbi"
else
    info "fbi not available"
fi

if command -v feh &> /dev/null; then
    optional_pass "feh available (X11 image viewer)"
    [ "$DISPLAY_METHOD" = "none" ] && DISPLAY_METHOD="feh"
else
    info "feh not available"
fi

if [ "$DISPLAY_METHOD" = "none" ]; then
    optional_warn "No image viewer found - will use RetroArch pause + OSD message"
else
    info "Will use: $DISPLAY_METHOD"
fi

# =============================================================================
# Test 8: Controller Devices (CRITICAL if using hotkeys)
# =============================================================================
echo
echo "--- Test 8: Controller Devices --- $(critical)"
if [ -d "/dev/input" ]; then
    critical_pass "/dev/input exists"

    if [ "$EVDEV_OK" = "1" ]; then
        echo "  Available game controllers:"
        python3 -c "
import evdev
for path in evdev.list_devices():
    try:
        dev = evdev.InputDevice(path)
        name = dev.name.lower()
        # Filter to likely game controllers
        if any(x in name for x in ['controller', 'gamepad', 'joystick', '8bitdo', 'xbox', 'playstation', 'wireless']):
            if 'mouse' not in name and 'keyboard' not in name and 'motion' not in name and 'touchpad' not in name:
                print(f'    {path}: {dev.name}')
    except:
        pass
" 2>/dev/null
        echo
        info "Update config.json 'controller_device' with your controller path"
    else
        info "evdev not available - list devices with: ls /dev/input/event*"
    fi
else
    critical_fail "/dev/input not found"
fi

# =============================================================================
# Test 9: Config File Check
# =============================================================================
echo
echo "--- Test 9: Configuration ---"
CONFIG_FILE="/userdata/system/ai-hints/config.json"
if [ -f "$CONFIG_FILE" ]; then
    critical_pass "Config file exists"

    # Check if API key is set
    if grep -q "YOUR_API_KEY_HERE" "$CONFIG_FILE" 2>/dev/null; then
        critical_fail "API key not configured (still has placeholder)"
        info "Edit config.json and add your Anthropic API key"
    else
        critical_pass "API key appears to be configured"
    fi
else
    critical_fail "Config file not found: $CONFIG_FILE"
fi

# =============================================================================
# Summary
# =============================================================================
echo
echo "========================================"
echo "  Test Summary"
echo "========================================"
echo
echo -e "  Critical tests: ${GREEN}$CRITICAL_PASS passed${NC}, ${RED}$CRITICAL_FAIL failed${NC}"
echo -e "  Optional tests: ${GREEN}$OPTIONAL_PASS passed${NC}, ${YELLOW}$OPTIONAL_WARN warnings${NC}"
echo

if [ $CRITICAL_FAIL -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ALL CRITICAL TESTS PASSED!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo
    echo "You can start the service:"
    echo "  batocera-services start ai_hint"
    echo
    echo "Then test with a game running:"
    echo "  /userdata/system/ai-hints/trigger-hint.sh request"
    echo
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  $CRITICAL_FAIL CRITICAL TEST(S) FAILED${NC}"
    echo -e "${RED}========================================${NC}"
    echo
    echo "Please fix the failed critical tests before starting the service."
    echo
fi

# Show controller recommendation if found
if [ "$EVDEV_OK" = "1" ]; then
    CONTROLLER=$(python3 -c "
import evdev
for path in evdev.list_devices():
    try:
        dev = evdev.InputDevice(path)
        name = dev.name.lower()
        if any(x in name for x in ['controller', 'gamepad', '8bitdo', 'xbox']) and 'mouse' not in name and 'keyboard' not in name:
            print(path)
            break
    except:
        pass
" 2>/dev/null)
    if [ -n "$CONTROLLER" ]; then
        echo "Recommended controller_device for config.json:"
        echo "  $CONTROLLER"
        echo
    fi
fi
