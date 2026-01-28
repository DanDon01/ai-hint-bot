# Batocera AI Hint System - Project Plan

## Overview

A background daemon for Batocera that provides on-demand AI-powered hints for retro games. Player presses a hotkey, the system captures a screenshot, sends it to Claude's or OpenAIs API, and displays the hint on demand without interrupting gameplay.

---

## Hardware & Environment

- **Target Device:** HP EliteDesk G3 running Batocera
- **Development Machine:** Windows PC with VSCode + Claude terminal
- **Network:** Both machines on same network
- **Controller:** TBD (need to identify for evdev)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BATOCERA SYSTEM                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐      ┌──────────────────────────────────┐ │
│  │   ai-hint-      │      │          RetroArch               │ │
│  │   daemon.py     │◄────►│   (Network Commands :55355)      │ │
│  │                 │      │                                  │ │
│  │  - evdev        │      │   - GET_STATUS                   │ │
│  │    hotkey       │      │   - SHOW_MESG                    │ │
│  │    listener     │      │   - SAVE_STATE / LOAD_STATE      │ │
│  │                 │      │   - Screenshot capture           │ │
│  │  - Claude API   │      │                                  │ │
│  │    calls        │      └──────────────────────────────────┘ │
│  │                 │                                           │
│  │  - PNG hint     │      ┌──────────────────────────────────┐ │
│  │    renderer     │      │     /userdata/system/            │ │
│  │                 │      │     └── ai-hints/                │ │
│  └─────────────────┘      │         ├── current-hint.png     │ │
│                           │         └── archive/             │ │
│                           │             └── [SYSTEM]/        │ │
│                           │                 └── [GAME]/      │ │
│                           └──────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTPS
                    ┌───────────────────┐
                    │  Claude API       │
                    │  (Vision Model)   │
                    └───────────────────┘
```

---

## User Flow

1. Player is stuck in game
2. Player presses **Hotkey 1** (Select+L1)
3. System silently captures screenshot + fetches game info
4. API call happens in background - game continues normally
5. When response arrives, notification appears: **"Hint Ready!"**
6. Player presses **Hotkey 2** (Select+R1) when convenient
7. Game savestates, hint image displays fullscreen
8. Player reads hint, presses any button
9. Savestate loads, player continues exactly where they were

---

## Phase 1: Connectivity & Capability Testing

Before writing any daemon code, verify every component works independently.

### Test 1.1: SSH Access to Batocera

```bash
# From Windows terminal (PowerShell or CMD)
ssh root@<BATOCERA_IP>
# Default password is usually blank or 'linux'
```

**Success criteria:** You get a shell prompt on Batocera.

**Note Batocera IP:** ____________

---

### Test 1.2: RetroArch Network Commands Enabled

On Batocera via SSH:

```bash
# Check if network commands are enabled in config
grep "network_cmd_enable" /userdata/system/configs/retroarch/retroarch.cfg
```

If not enabled or missing, add/edit:

```bash
nano /userdata/system/configs/retroarch/retroarch.cfg
# Add or set:
# network_cmd_enable = "true"
# network_cmd_port = "55355"
```

Then restart RetroArch or reboot.

---

### Test 1.3: GET_STATUS While Game Running

1. Launch any game from EmulationStation
2. From SSH session (or second terminal):

```bash
echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 55355
```

**Success criteria:** Returns something like `GET_STATUS PLAYING GameName,core_name,crc32=XXXX`

**Record output format:** 
```
_________________________________________________________________
```

---

### Test 1.4: SHOW_MESG Notification

With game still running:

```bash
echo -n "SHOW_MESG Hint Ready!" | nc -u -w1 127.0.0.1 55355
```

**Success criteria:** Text appears on screen over the game.

**Notes on appearance (duration, position, readability):**
```
_________________________________________________________________
```

---

### Test 1.5: Screenshot Capture

```bash
echo -n "SCREENSHOT" | nc -u -w1 127.0.0.1 55355
```

**Success criteria:** Screenshot saved.

**Find where it saved:**

```bash
find /userdata -name "*.png" -mmin -1 2>/dev/null
```

**Screenshot location:** ____________

---

### Test 1.6: Savestate / Loadstate Commands

```bash
# Save to slot 9 (we'll reserve this for hint system)
echo -n "SAVE_STATE_SLOT 9" | nc -u -w1 127.0.0.1 55355
echo -n "SAVE_STATE" | nc -u -w1 127.0.0.1 55355

# Do something in game to change state...

# Load it back
echo -n "LOAD_STATE_SLOT 9" | nc -u -w1 127.0.0.1 55355
echo -n "LOAD_STATE" | nc -u -w1 127.0.0.1 55355
```

**Success criteria:** Game returns to exact saved moment.

**Notes on speed/reliability:**
```
_________________________________________________________________
```

---

### Test 1.7: Python Availability

```bash
python3 --version

# Check for required modules
python3 -c "import socket; print('socket OK')"
python3 -c "import json; print('json OK')"
python3 -c "import subprocess; print('subprocess OK')"

# Check for optional modules (may need installing)
python3 -c "import evdev; print('evdev OK')" 2>/dev/null || echo "evdev NOT FOUND"
python3 -c "import requests; print('requests OK')" 2>/dev/null || echo "requests NOT FOUND"  
python3 -c "from PIL import Image; print('PIL OK')" 2>/dev/null || echo "PIL NOT FOUND"
```

**Python version:** ____________

**Available modules:**
- [ ] socket (built-in, should always work)
- [ ] json (built-in, should always work)
- [ ] subprocess (built-in, should always work)
- [ ] evdev
- [ ] requests
- [ ] PIL/Pillow

---

### Test 1.8: evdev Controller Detection

If evdev is available:

```bash
python3 -c "
import evdev
devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
for device in devices:
    print(f'{device.path}: {device.name}')
"
```

**Your controller device path:** ____________

**Controller name:** ____________

If evdev is NOT available, we'll use an alternative approach (polling /dev/input directly or RetroArch hotkey-to-script).

---

### Test 1.9: Network Access to Claude API

```bash
# Test outbound HTTPS
curl -I https://api.anthropic.com 2>/dev/null | head -5

# Or with Python
python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('https://api.anthropic.com', timeout=5)
    print('API reachable')
except Exception as e:
    print(f'Failed: {e}')
"
```

**Success criteria:** Connection succeeds (even if 401 unauthorized - that's fine, means we reached it).

---

### Test 1.10: Persistent Storage Location

```bash
# Verify /userdata/system is writable and persistent
mkdir -p /userdata/system/ai-hints/archive
echo "test" > /userdata/system/ai-hints/test.txt
cat /userdata/system/ai-hints/test.txt
rm /userdata/system/ai-hints/test.txt
```

**Success criteria:** File creates, reads, deletes without permission errors.

---

### Test 1.11: custom.sh Boot Script

```bash
# Check if custom.sh exists
ls -la /userdata/system/custom.sh 2>/dev/null || echo "Does not exist yet"

# Create or edit it
cat > /userdata/system/custom.sh << 'EOF'
#!/bin/bash
echo "Custom script ran at $(date)" >> /userdata/system/boot.log
EOF

chmod +x /userdata/system/custom.sh

# Reboot and verify
reboot
```

After reboot:

```bash
cat /userdata/system/boot.log
```

**Success criteria:** Log file shows boot timestamp.

---

## Phase 2: Manual Integration Test

Before writing the daemon, manually execute the entire flow step by step.

### Test 2.1: Full Manual Flow

1. **Start a game** (something you know well, eg Super Mario World)

2. **Get game info:**
   ```bash
   echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 55355
   ```
   Record: ____________

3. **Take screenshot:**
   ```bash
   echo -n "SCREENSHOT" | nc -u -w1 127.0.0.1 55355
   ```

4. **Copy screenshot to PC for API testing:**
   ```bash
   # On Windows, use SCP:
   scp root@<BATOCERA_IP>:/path/to/screenshot.png ./test-screenshot.png
   ```

5. **Test Claude API manually** (on Windows PC):
   - Use the test screenshot
   - Send to Claude with vision
   - Verify you get a useful hint response

6. **Create a test hint image** (can be simple text on colored background for now)

7. **Test the savestate sandwich:**
   ```bash
   # Save
   echo -n "SAVE_STATE_SLOT 9" | nc -u -w1 127.0.0.1 55355
   echo -n "SAVE_STATE" | nc -u -w1 127.0.0.1 55355
   
   # Quit game
   echo -n "QUIT" | nc -u -w1 127.0.0.1 55355
   
   # How do we display an image and wait for input?
   # Option A: Use RetroArch's built-in image viewer core
   # Option B: Use a framebuffer image viewer (fbi, feh)
   # Test both...
   
   # Then restore
   # Need to reload the game + core first, then:
   echo -n "LOAD_STATE_SLOT 9" | nc -u -w1 127.0.0.1 55355
   echo -n "LOAD_STATE" | nc -u -w1 127.0.0.1 55355
   ```

**Critical question to answer:** What's the cleanest way to display the hint image and wait for dismissal? Options:

- [ ] RetroArch imageviewer core (may require content loading dance)
- [ ] fbi (framebuffer image viewer - may be available)
- [ ] Python pygame/tkinter fullscreen (if display is accessible)
- [ ] Keep RetroArch running, just PAUSE and overlay somehow

**Notes from testing:**
```
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
```

---

## Phase 3: Daemon Development

Once all tests pass, build the daemon incrementally.

### 3.1 File Structure

```
/userdata/system/
├── custom.sh                      # Boot launcher
├── ai-hints/
│   ├── daemon.py                  # Main daemon script
│   ├── config.json                # API key, settings
│   ├── hint-template.png          # Background for hint rendering (optional)
│   ├── current-hint.png           # Latest rendered hint
│   └── archive/
│       └── [SYSTEM]/
│           └── [GAME]/
│               └── [timestamp].png
```

### 3.2 config.json Structure

```json
{
    "api_key": "sk-ant-xxxxx",
    "hotkey_request": ["BTN_SELECT", "BTN_TL"],
    "hotkey_view": ["BTN_SELECT", "BTN_TR"],
    "controller_device": "/dev/input/event0",
    "savestate_slot": 9,
    "notification_text": "Hint Ready!",
    "prompt_template": "System: {system}\nGame: {game}\n\nThe player is stuck in this retro game. Based on the screenshot, provide a brief, spoiler-minimal hint about what to do next. Keep it to 2-3 sentences. Be specific to what's visible on screen."
}
```

### 3.3 Daemon Components (Build Order)

1. **Config loader** - Read settings from config.json
2. **RetroArch commander** - Send UDP commands, parse responses
3. **Screenshot capturer** - Trigger and locate screenshots
4. **Game info parser** - Extract system/game from GET_STATUS
5. **API caller** - Send screenshot + prompt to Claude, get response
6. **Hint renderer** - Turn text response into styled PNG
7. **Archive manager** - Save hints to correct folder structure
8. **Hint viewer** - Display image, wait for dismiss, return to game
9. **Hotkey listener** - Detect button combos via evdev
10. **Main loop** - Tie it all together

### 3.4 Daemon Pseudocode

```python
# daemon.py pseudocode

def main():
    config = load_config()
    
    # Start hotkey listener in separate thread
    hotkey_thread = start_hotkey_listener(config, on_request_hint, on_view_hint)
    
    # Main loop just keeps process alive
    while True:
        time.sleep(1)

def on_request_hint():
    """Called when request hotkey combo detected"""
    status = retroarch_command("GET_STATUS")
    game, system = parse_status(status)
    
    retroarch_command("SCREENSHOT")
    screenshot_path = find_latest_screenshot()
    
    # Async API call - don't block
    threading.Thread(target=process_hint_request, args=(screenshot_path, game, system)).start()

def process_hint_request(screenshot_path, game, system):
    """Runs in background thread"""
    response = call_claude_api(screenshot_path, game, system)
    hint_text = response.content
    
    # Render and save
    hint_image = render_hint_image(hint_text, game, system)
    save_current_hint(hint_image)
    archive_hint(hint_image, game, system)
    
    # Notify player
    retroarch_command("SHOW_MESG Hint Ready!")

def on_view_hint():
    """Called when view hotkey combo detected"""
    # Save current state
    retroarch_command(f"SAVE_STATE_SLOT {HINT_SLOT}")
    retroarch_command("SAVE_STATE")
    
    # Display hint (implementation TBD based on Phase 2 testing)
    display_hint_image("/userdata/system/ai-hints/current-hint.png")
    wait_for_dismiss()
    
    # Restore state
    retroarch_command(f"LOAD_STATE_SLOT {HINT_SLOT}")
    retroarch_command("LOAD_STATE")
```

---

## Phase 4: Testing & Refinement

- Test with multiple systems (SNES, Genesis, PSX, etc.)
- Test savestate reliability across different cores
- Tune hint rendering (font size, colors, readability on TV)
- Handle edge cases (no game running, API timeout, etc.)
- Measure and minimize any performance impact

---

## Phase 5: Future Enhancements (Out of Scope for MVP)

- [ ] Web UI for browsing hint archive
- [ ] Previous hints viewer (in-game gallery)
- [ ] Voice readout option (ElevenLabs TTS)
- [ ] Difficulty levels for hints (vague → specific)
- [ ] Game-specific prompt tuning
- [ ] Local LLM fallback for offline use

---

## Open Questions to Resolve

1. **Hint display method:** What's the cleanest way to show a fullscreen image and wait for dismiss without breaking the game?

2. **evdev availability:** If not available, what's the fallback hotkey detection method?

3. **Missing Python modules:** Can we install them on Batocera, or need to bundle/vendorize?

4. **Screenshot location:** Where does RetroArch save screenshots on Batocera specifically?

5. **API latency:** How long does Claude vision API typically take? Need to manage user expectations.

---

## Reference: RetroArch Network Commands

```
GET_STATUS          - Returns current playback state and content info
SHOW_MESG <text>    - Display on-screen notification
SCREENSHOT          - Capture screenshot
SAVE_STATE          - Save to current slot
LOAD_STATE          - Load from current slot
SAVE_STATE_SLOT <n> - Set save slot
LOAD_STATE_SLOT <n> - Set load slot  
PAUSE_TOGGLE        - Pause/unpause
QUIT                - Close content
```

Port: 55355 (UDP)

---

## Reference: Batocera Paths

```
/userdata/                      # Persistent user data partition
/userdata/system/               # System configs and scripts
/userdata/system/custom.sh      # Boot script
/userdata/system/configs/       # App configs
/userdata/roms/                 # ROM storage
/userdata/screenshots/          # Default screenshot location (verify)
```

---

## Getting Started Checklist

- [ ] Get Batocera IP address
- [ ] Verify SSH access
- [ ] Run all Phase 1 tests
- [ ] Document results in this file
- [ ] Run Phase 2 manual integration test
- [ ] Decide on hint display method
- [ ] Obtain Claude API key
- [ ] Begin Phase 3 development
