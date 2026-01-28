# Batocera AI Hint System - Project Plan

## Project Status: PHASE 3 COMPLETE - Ready for Testing

**Last Updated:** 2026-01-28

---

## Overview

A background daemon for Batocera that provides on-demand AI-powered hints for retro games. Player presses a hotkey, the system captures a screenshot, sends it to Claude's or OpenAI's API, and displays the hint on demand without interrupting gameplay.

---

## Hardware & Environment

| Item | Value |
|------|-------|
| **Target Device** | HP EliteDesk G3 running Batocera |
| **Batocera IP** | 192.168.0.129 |
| **Python Version** | 3.12.8 |
| **Development Machine** | Windows PC with VSCode + Claude Code |
| **Network** | Both machines on same local network |
| **SSH Access** | Verified working (root@192.168.0.129) |
| **Controller** | TBD (need to identify for evdev) |

---

## Current Progress

### Completed

- [x] **Phase 1:** Basic connectivity testing (SSH, Python version)
- [x] **Phase 3:** Full daemon development
  - [x] Config loader with defaults
  - [x] RetroArch UDP commander
  - [x] Screenshot capture and detection
  - [x] Game info parser (core-to-system mapping)
  - [x] Claude API client (with OpenAI support)
  - [x] Hint image renderer (PIL + ImageMagick fallback)
  - [x] Archive manager
  - [x] Hint viewer (fbi/feh/RetroArch fallback)
  - [x] Hotkey listener (evdev + file-based fallback)
  - [x] Rate limiting (10 calls/day default)
  - [x] Detailed logging system
  - [x] Batocera service script
  - [x] Deploy scripts (PowerShell + Batch)
  - [x] README documentation

### Remaining

- [ ] **Phase 1:** Complete remaining connectivity tests on Batocera
- [ ] **Phase 2:** Manual integration testing
- [ ] **Phase 4:** Real-world testing and refinement
- [ ] Identify controller device path
- [ ] Test hint display methods (fbi/feh availability)
- [ ] Verify RetroArch network commands work

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BATOCERA SYSTEM                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐      ┌──────────────────────────────────┐ │
│  │   daemon.py     │      │          RetroArch               │ │
│  │                 │◄────►│   (Network Commands :55355)      │ │
│  │  - Rate limiter │      │                                  │ │
│  │    (10/day)     │      │   - GET_STATUS                   │ │
│  │                 │      │   - SHOW_MSG                     │ │
│  │  - evdev        │      │   - SAVE_STATE / LOAD_STATE      │ │
│  │    hotkeys      │      │   - SCREENSHOT                   │ │
│  │                 │      │                                  │ │
│  │  - Claude/GPT   │      └──────────────────────────────────┘ │
│  │    API client   │                                           │
│  │                 │      ┌──────────────────────────────────┐ │
│  │  - PNG hint     │      │     /userdata/system/ai-hints/   │ │
│  │    renderer     │      │     ├── config.json              │ │
│  │                 │      │     ├── daemon.log               │ │
│  │  - Detailed     │      │     ├── usage.log                │ │
│  │    logging      │      │     ├── usage_counter.json       │ │
│  │                 │      │     ├── current-hint.png         │ │
│  └─────────────────┘      │     └── archive/[SYSTEM]/[GAME]/ │ │
│                           └──────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTPS
                    ┌───────────────────┐
                    │  Claude API       │
                    │  (Vision Model)   │
                    │  - or -           │
                    │  OpenAI API       │
                    │  (GPT-4 Vision)   │
                    └───────────────────┘
```

---

## User Flow

1. Player is stuck in game
2. Player presses **Select + L1** to request hint
3. System captures screenshot + fetches game info
4. API call happens in background - game continues normally
5. When response arrives, notification appears: **"Hint Ready!"**
6. Player presses **Select + R1** when convenient
7. Game savestates, hint image displays fullscreen
8. Player reads hint, presses any button
9. Savestate loads, player continues exactly where they were

**Rate Limit:** 10 hints per day (configurable). Shows "Daily limit reached!" when exhausted.

---

## File Structure (Development)

```
ai-hint-bot/                          # Windows development repo
├── README.md                         # Install & usage docs
├── .gitignore                        # Excludes secrets, logs
├── batocera-ai-hint-system-plan.md   # This file
├── src/
│   ├── daemon.py                     # Main daemon (~1100 lines)
│   └── config.example.json           # Template config
├── service/
│   └── ai_hint                       # Batocera service script
├── scripts/
│   ├── deploy.ps1                    # PowerShell deploy
│   ├── deploy.bat                    # Batch deploy
│   ├── install.sh                    # On-device installer
│   ├── test-components.sh            # Component tests
│   └── trigger-hint.sh               # Manual trigger
└── docs/
    └── batocera-reference.md         # Batocera API reference
```

## File Structure (Batocera - After Deploy)

```
/userdata/system/
├── services/
│   └── ai_hint                       # Service script
└── ai-hints/
    ├── daemon.py                     # Main daemon
    ├── config.json                   # Config WITH your API key
    ├── config.example.json           # Template (safe)
    ├── daemon.log                    # Main event log
    ├── usage.log                     # JSON usage analytics
    ├── usage_counter.json            # Daily rate limit state
    ├── current-hint.png              # Latest hint image
    ├── install.sh                    # Installer
    ├── test-components.sh            # Test script
    ├── trigger-hint.sh               # Manual trigger
    └── archive/
        └── [System]/
            └── [Game]/
                └── [timestamp].png   # Archived hints
```

---

## Configuration

```json
{
  "api_provider": "anthropic",
  "api_key": "YOUR_API_KEY_HERE",
  "model": "claude-sonnet-4-20250514",
  "daily_limit": 10,
  "hotkey_request": ["BTN_SELECT", "BTN_TL"],
  "hotkey_view": ["BTN_SELECT", "BTN_TR"],
  "controller_device": "/dev/input/event0",
  "retroarch_host": "127.0.0.1",
  "retroarch_port": 55355,
  "savestate_slot": 9,
  "screenshot_dir": "/userdata/screenshots",
  "hints_dir": "/userdata/system/ai-hints",
  "notification_ready": "Hint Ready! Press Select+R1 to view.",
  "notification_generating": "Generating hint...",
  "notification_error": "Hint failed. Try again.",
  "notification_limit_reached": "Daily limit reached! ({used}/{limit})",
  "hint_font_size": 32,
  "hint_bg_color": [32, 32, 32],
  "hint_text_color": [255, 255, 255],
  "hint_width": 1280,
  "hint_height": 720,
  "debug": false
}
```

---

## Phase 1: Connectivity & Capability Testing

### Test 1.1: SSH Access to Batocera

```bash
ssh root@192.168.0.129
# Password: linux
```

**Status:** PASSED

---

### Test 1.2: RetroArch Network Commands Enabled

```bash
grep "network_cmd_enable" /userdata/system/batocera.conf
```

If not enabled, deploy script adds:
```
global.retroarch.network_cmd_enable=true
global.retroarch.network_cmd_port=55355
```

**Status:** TBD (deploy script will configure)

---

### Test 1.3: GET_STATUS While Game Running

```bash
echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 55355
```

**Expected:** `GET_STATUS PLAYING GameName,core_name`

**Status:** TBD
**Result:** ____________

---

### Test 1.4: SHOW_MSG Notification

```bash
echo -n "SHOW_MSG Test message!" | nc -u -w1 127.0.0.1 55355
```

**Note:** Command is `SHOW_MSG` (not `SHOW_MESG`)

**Status:** TBD
**Notes:** ____________

---

### Test 1.5: Screenshot Capture

```bash
echo -n "SCREENSHOT" | nc -u -w1 127.0.0.1 55355
find /userdata/screenshots -name "*.png" -mmin -1
```

**Status:** TBD
**Screenshot location:** ____________

---

### Test 1.6: Savestate Commands

```bash
echo -n "SAVE_STATE_SLOT 9" | nc -u -w1 127.0.0.1 55355
echo -n "SAVE_STATE" | nc -u -w1 127.0.0.1 55355
# Change something in game...
echo -n "LOAD_STATE_SLOT 9" | nc -u -w1 127.0.0.1 55355
echo -n "LOAD_STATE" | nc -u -w1 127.0.0.1 55355
```

**Status:** TBD
**Notes:** ____________

---

### Test 1.7: Python Availability

```bash
python3 --version
```

**Status:** PASSED
**Python version:** 3.12.8

**Module Check:**
```bash
python3 -c "import evdev; print('evdev OK')" 2>/dev/null || echo "NOT FOUND"
python3 -c "from PIL import Image; print('PIL OK')" 2>/dev/null || echo "NOT FOUND"
```

**Status:** TBD
- [ ] evdev available?
- [ ] PIL available?

---

### Test 1.8: Controller Detection

```bash
python3 -c "
import evdev
for path in evdev.list_devices():
    dev = evdev.InputDevice(path)
    print(f'{path}: {dev.name}')
"
```

**Status:** TBD
**Controller path:** ____________
**Controller name:** ____________

---

### Test 1.9: Network Access to Claude API

```bash
curl -I https://api.anthropic.com 2>/dev/null | head -3
```

**Status:** TBD (probably passed if SSH works)

---

### Test 1.10: Persistent Storage

```bash
mkdir -p /userdata/system/ai-hints/archive
echo "test" > /userdata/system/ai-hints/test.txt
cat /userdata/system/ai-hints/test.txt
rm /userdata/system/ai-hints/test.txt
```

**Status:** TBD

---

## Phase 2: Deploy & Initial Testing

### Step 1: Deploy from Windows

```powershell
cd D:\AI\ai-hint-bot
.\scripts\deploy.ps1 192.168.0.129
```

### Step 2: Configure API Key

```bash
ssh root@192.168.0.129
nano /userdata/system/ai-hints/config.json
# Change "YOUR_API_KEY_HERE" to your actual Anthropic API key
```

### Step 3: Run Component Tests

```bash
/userdata/system/ai-hints/test-components.sh
```

### Step 4: Start Service

```bash
batocera-services start ai_hint
```

### Step 5: Check Logs

```bash
tail -f /userdata/system/ai-hints/daemon.log
```

### Step 6: Test with Manual Trigger

```bash
# Start a game first, then in SSH:
/userdata/system/ai-hints/trigger-hint.sh request
# Watch for "Hint Ready!" notification
/userdata/system/ai-hints/trigger-hint.sh view
```

---

## Phase 3: Daemon Development

**STATUS: COMPLETE**

All components implemented:

| Component | Status | Notes |
|-----------|--------|-------|
| Config loader | Done | JSON config with defaults |
| RetroArch commander | Done | UDP socket, all commands |
| Screenshot manager | Done | Capture + find latest |
| Game info parser | Done | Core-to-system mapping |
| AI client | Done | Claude + OpenAI support |
| Hint renderer | Done | PIL + ImageMagick fallback |
| Archive manager | Done | System/Game/timestamp structure |
| Hint viewer | Done | fbi/feh/RetroArch fallback |
| Hotkey listener | Done | evdev + file-based fallback |
| Rate limiter | Done | Daily limits, persistent counter |
| Logger | Done | Multi-level, usage tracking |
| Service script | Done | Batocera services framework |
| Deploy scripts | Done | PowerShell + Batch |

---

## Phase 4: Testing & Refinement

- [ ] Test with SNES games
- [ ] Test with Genesis games
- [ ] Test with PlayStation games
- [ ] Test with N64 games
- [ ] Verify savestate reliability across cores
- [ ] Tune hint rendering for TV readability
- [ ] Test rate limiting across day boundary
- [ ] Verify logging captures all events
- [ ] Test error handling (no game, API timeout, etc.)

---

## Phase 5: Future Enhancements (Post-MVP)

- [ ] Web UI for browsing hint archive
- [ ] Previous hints viewer (in-game gallery)
- [ ] Voice readout option (ElevenLabs TTS)
- [ ] Difficulty levels for hints (vague -> specific)
- [ ] Game-specific prompt tuning
- [ ] Local LLM fallback for offline use
- [ ] Cost tracking in usage logs

---

## Open Questions

1. **Controller device:** Need to identify the correct `/dev/input/eventX` path

2. **Hint display:** Which method is available on Batocera?
   - [ ] fbi (framebuffer) - preferred
   - [ ] feh (X11)
   - [ ] RetroArch pause (fallback)

3. **evdev availability:** If not available, file-based triggers will work

4. **Screenshot location:** Verify `/userdata/screenshots/` is correct

---

## Quick Reference

### Deploy Command
```powershell
.\scripts\deploy.ps1 192.168.0.129
```

### SSH Access
```bash
ssh root@192.168.0.129
```

### Service Commands
```bash
batocera-services start ai_hint
batocera-services stop ai_hint
batocera-services status ai_hint
```

### View Logs
```bash
tail -f /userdata/system/ai-hints/daemon.log
cat /userdata/system/ai-hints/usage_counter.json
```

### Manual Triggers
```bash
/userdata/system/ai-hints/trigger-hint.sh request
/userdata/system/ai-hints/trigger-hint.sh view
```

### RetroArch Commands (for testing)
```bash
echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 55355
echo -n "SHOW_MSG Hello!" | nc -u -w1 127.0.0.1 55355
echo -n "SCREENSHOT" | nc -u -w1 127.0.0.1 55355
```

---

## Changelog

### 2026-01-28
- Initial daemon development complete
- Added rate limiting (10 calls/day)
- Added detailed logging (daemon.log, usage.log)
- Created deploy scripts
- Created README documentation
- Batocera IP confirmed: 192.168.0.129
- Python version confirmed: 3.12.8
- SSH access confirmed working
