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
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "       $1"; }

# Test 1: Python
echo "--- Test 1: Python Environment ---"
if command -v python3 &> /dev/null; then
    VERSION=$(python3 --version 2>&1)
    pass "Python3 found: $VERSION"
else
    fail "Python3 not found"
fi

# Test built-in modules
for module in socket json subprocess os threading urllib.request base64; do
    if python3 -c "import $module" 2>/dev/null; then
        pass "Module: $module"
    else
        fail "Module: $module"
    fi
done

# Test optional modules
echo
echo "--- Test 2: Optional Modules ---"
if python3 -c "import evdev" 2>/dev/null; then
    pass "evdev available (controller hotkeys will work)"
else
    warn "evdev not available (will use file-based triggers)"
fi

if python3 -c "from PIL import Image" 2>/dev/null; then
    pass "PIL/Pillow available (full hint rendering)"
else
    warn "PIL not available (will try ImageMagick fallback)"
fi

if command -v convert &> /dev/null; then
    pass "ImageMagick available"
else
    warn "ImageMagick not available"
fi

# Test 3: RetroArch Network Commands
echo
echo "--- Test 3: RetroArch Network Commands ---"
echo "(Start a game first for full test)"

# Check if netcat is available
if command -v nc &> /dev/null; then
    pass "netcat (nc) available"

    # Try GET_STATUS
    RESPONSE=$(echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 55355 2>/dev/null)
    if [ -n "$RESPONSE" ]; then
        pass "GET_STATUS responded: $RESPONSE"
    else
        warn "GET_STATUS no response (is a game running? network commands enabled?)"
        info "Enable in batocera.conf: global.retroarch.network_cmd_enable=true"
    fi
else
    warn "netcat not available, testing with Python..."
    python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
s.sendto(b'GET_STATUS', ('127.0.0.1', 55355))
try:
    data, _ = s.recvfrom(4096)
    print('GET_STATUS responded:', data.decode())
except socket.timeout:
    print('No response (game running? commands enabled?)')
"
fi

# Test 4: Screenshot Directory
echo
echo "--- Test 4: Screenshot Directory ---"
SCREENSHOT_DIR="/userdata/screenshots"
if [ -d "$SCREENSHOT_DIR" ]; then
    pass "Screenshot directory exists: $SCREENSHOT_DIR"
    COUNT=$(find "$SCREENSHOT_DIR" -name "*.png" 2>/dev/null | wc -l)
    info "Contains $COUNT PNG files"
else
    warn "Screenshot directory not found"
    info "It will be created when RetroArch takes first screenshot"
fi

# Test 5: Hints Directory
echo
echo "--- Test 5: Hints Directory ---"
HINTS_DIR="/userdata/system/ai-hints"
if [ -d "$HINTS_DIR" ]; then
    pass "Hints directory exists: $HINTS_DIR"
else
    mkdir -p "$HINTS_DIR"
    pass "Hints directory created: $HINTS_DIR"
fi

if touch "$HINTS_DIR/test_write" 2>/dev/null; then
    rm "$HINTS_DIR/test_write"
    pass "Hints directory is writable"
else
    fail "Cannot write to hints directory"
fi

# Test 6: Network Access
echo
echo "--- Test 6: Network Access (API) ---"
if command -v curl &> /dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://api.anthropic.com 2>/dev/null)
    if [ "$HTTP_CODE" = "000" ]; then
        fail "Cannot reach api.anthropic.com (no network?)"
    else
        pass "api.anthropic.com reachable (HTTP $HTTP_CODE)"
    fi
else
    python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('https://api.anthropic.com', timeout=5)
    print('api.anthropic.com reachable')
except Exception as e:
    print(f'Cannot reach API: {e}')
"
fi

# Test 7: Display Methods
echo
echo "--- Test 7: Display Methods ---"
if command -v fbi &> /dev/null; then
    pass "fbi available (framebuffer image viewer)"
else
    warn "fbi not available"
fi

if command -v feh &> /dev/null; then
    pass "feh available (X11 image viewer)"
else
    warn "feh not available"
fi

# Test 8: Controller Devices
echo
echo "--- Test 8: Controller Devices ---"
if [ -d "/dev/input" ]; then
    pass "/dev/input exists"

    if python3 -c "import evdev" 2>/dev/null; then
        echo "  Available input devices:"
        python3 -c "
import evdev
for path in evdev.list_devices():
    try:
        dev = evdev.InputDevice(path)
        print(f'    {path}: {dev.name}')
    except:
        pass
"
    else
        info "List /dev/input/event* manually to find controller"
        ls -la /dev/input/event* 2>/dev/null | head -10
    fi
else
    fail "/dev/input not found"
fi

# Summary
echo
echo "========================================"
echo "  Test Summary"
echo "========================================"
echo
echo "If all critical tests pass, run the installer:"
echo "  ./install.sh"
echo
echo "Then edit config.json with your API key and start the service."
echo
