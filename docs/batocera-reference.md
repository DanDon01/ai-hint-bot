# Batocera Reference Documentation

Compiled from official Batocera wiki and libretro docs for the AI Hint System project.

---

## File System Structure

### Key Directories

| Path | Purpose |
|------|---------|
| `/userdata/` | Persistent user data partition (survives updates) |
| `/userdata/system/` | System configs, scripts, home directory (`~`) |
| `/userdata/roms/` | ROM storage, organized by system shortname |
| `/userdata/bios/` | BIOS files |
| `/userdata/screenshots/` | Default screenshot location |
| `/userdata/system/services/` | User-created services (v38+) |
| `/usr/share/batocera/services/` | System services (read-only) |

### Configuration Files

| File | Purpose |
|------|---------|
| `/userdata/system/batocera.conf` | Main Batocera configuration |
| `/userdata/system/configs/retroarch/retroarchcustom.cfg` | Custom RetroArch settings (persistent) |
| `/userdata/system/configs/retroarch/cores/retroarch-core-options.cfg` | Core-specific options |

**Important:** Batocera regenerates `retroarch.cfg` at each emulator launch. Use `retroarchcustom.cfg` for persistent settings or add to `batocera.conf` with syntax: `global.retroarch.<setting>=value`

---

## SSH Access

- **Username:** `root`
- **Default password:** `linux`
- **Connect:** `ssh root@batocera.local` or `ssh root@<IP_ADDRESS>`
- **Local terminal:** Press `Ctrl+Alt+F5` (return with `Ctrl+Alt+F2`)
- **Config:** Ensure `system.ssh.enabled=1` in `/userdata/system/batocera.conf`

---

## Services Framework (v38+)

Services replace the deprecated `custom.sh` for running background scripts.

### Creating a Service

1. Create script in `/userdata/system/services/` (no `.sh` extension)
2. Use UNIX line endings (LF, not CRLF)
3. Script receives `start` or `stop` as argument
4. Reboot or run `batocera-services start <servicename>`

### Filename Rules

- Valid: A-Z, a-z, underscores, digits (not first char)
- Invalid: dots, hyphens, spaces, special characters

### Service Template

```bash
#!/bin/bash

case "$1" in
    start)
        # Start your daemon here
        /userdata/system/ai-hints/daemon.py &
        ;;
    stop)
        # Stop your daemon here
        killall daemon.py 2>/dev/null
        ;;
    status)
        # Check if running
        pgrep -f daemon.py > /dev/null && echo "running" || echo "stopped"
        ;;
esac
```

### Management

- **CLI:** `batocera-services list`, `batocera-services start <name>`, `batocera-services stop <name>`
- **GUI:** Main Menu > System Settings > Services
- **Debug:** `bash -x batocera-services list`

### Legacy: custom.sh (Deprecated)

Still works but services are preferred:
- Location: `/userdata/system/custom.sh`
- Receives `start` or `stop` argument
- Runs after EmulationStation launches

---

## Boot Scripts (Alternative Locations)

| Script | When it runs |
|--------|--------------|
| `/boot/boot-custom.sh` | Earliest, before most services |
| `/boot/postshare.sh` | After userdata mounts, before EmulationStation |
| `/userdata/system/custom.sh` | Last, after EmulationStation launches |

---

## RetroArch Network Commands

### Enabling Network Commands

Add to `/userdata/system/configs/retroarch/retroarchcustom.cfg`:

```
network_cmd_enable = "true"
network_cmd_port = "55355"
```

Or add to `/userdata/system/batocera.conf`:

```
global.retroarch.network_cmd_enable=true
global.retroarch.network_cmd_port=55355
```

### Sending Commands

Commands are UDP packets to port 55355:

```bash
echo -n "COMMAND_NAME" | nc -u -w1 127.0.0.1 55355
```

### Available Commands

**Playback Control:**
- `PAUSE_TOGGLE` - Pause/unpause
- `FRAMEADVANCE` - Advance one frame
- `REWIND` - Rewind
- `FAST_FORWARD` - Fast forward
- `SLOWMOTION` - Slow motion

**State Management:**
- `SAVE_STATE` - Save to current slot
- `LOAD_STATE` - Load from current slot
- `SAVE_STATE_SLOT <n>` - Set save slot (0-9)
- `LOAD_STATE_SLOT <n>` - Set load slot (0-9)
- `STATE_SLOT_PLUS` - Next slot
- `STATE_SLOT_MINUS` - Previous slot

**Display:**
- `SCREENSHOT` - Capture screenshot
- `FULLSCREEN_TOGGLE` - Toggle fullscreen
- `SHADER_NEXT` / `SHADER_PREV` - Change shader
- `OVERLAY_NEXT` - Next overlay

**System:**
- `QUIT` - Close content and RetroArch
- `RESET` - Reset game
- `CLOSE_CONTENT` - Close game, keep RetroArch
- `MENU_TOGGLE` - Open/close menu

**Audio:**
- `MUTE` - Toggle mute
- `VOLUME_UP` / `VOLUME_DOWN` - Adjust volume

**Information:**
- `GET_STATUS` - Get current playback state and content info
- `GET_CONFIG_PARAM <param>` - Get config value
- `VERSION` - Get RetroArch version

**Notifications:**
- `SHOW_MSG <text>` - Display on-screen message (note: MSG not MESG)

**Memory Access:**
- `READ_CORE_MEMORY <address>` - Read memory
- `WRITE_CORE_MEMORY <address> <value>` - Write memory

---

## RetroArch Configuration via batocera.conf

### Syntax

Global settings:
```
global.retroarch.<setting>=value
```

Per-system settings:
```
<system_shortname>.retroarch.<setting>=value
```

Core options:
```
global.retroarchcore.<core_name>_<option>=value
```

### Example Settings

```
global.retroarch.network_cmd_enable=true
global.retroarch.network_cmd_port=55355
global.retroarch.savestate_auto_save=false
snes.retroarch.video_smooth=true
```

---

## Python on Batocera

Batocera includes Python 3. Check availability with:

```bash
python3 --version
```

### Standard Modules (Built-in)

These should always be available:
- `socket`
- `json`
- `subprocess`
- `os`
- `sys`
- `threading`
- `urllib.request`
- `base64`
- `time`

### Additional Modules (May Vary)

Check availability:
```bash
python3 -c "import evdev; print('evdev OK')" 2>/dev/null || echo "evdev NOT FOUND"
python3 -c "import requests; print('requests OK')" 2>/dev/null || echo "requests NOT FOUND"
python3 -c "from PIL import Image; print('PIL OK')" 2>/dev/null || echo "PIL NOT FOUND"
```

---

## Screenshots

Default location: `/userdata/screenshots/`

RetroArch saves screenshots with naming pattern based on content name and timestamp.

To find recent screenshots:
```bash
find /userdata/screenshots -name "*.png" -mmin -5
```

---

## Useful Commands

```bash
# System info
batocera-info

# List services
batocera-services list
batocera-services list user

# Check running processes
ps aux | grep python

# View logs
tail -f /var/log/messages

# Network test
curl -I https://api.anthropic.com

# Find files modified recently
find /userdata -mmin -5 -type f
```

---

## Important Notes

1. **Line Endings:** All scripts must use UNIX line endings (LF). Windows-style CRLF will cause execution failures.

2. **Persistence:** Only `/userdata/` survives system updates. Don't put custom files elsewhere.

3. **RetroArch Config Regeneration:** `retroarch.cfg` is regenerated on each launch. Use `retroarchcustom.cfg` or `batocera.conf` for persistent settings.

4. **Services vs custom.sh:** Services (v38+) are preferred over custom.sh for better management and control.

5. **Security:** Batocera is not designed as a secure OS. Avoid exposing to public networks.
