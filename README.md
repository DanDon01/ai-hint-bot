# Batocera AI Hint System

A background daemon for Batocera that provides on-demand AI-powered hints for retro games. Press a hotkey while stuck, get a contextual hint from Claude or GPT-4 based on your current screenshot.

## How It Works

1. Player gets stuck in a game
2. Press **Select + L1** to request a hint
3. System captures screenshot and sends to AI in background
4. When ready, notification appears: "Hint Ready!"
5. Press **Select + R1** to view the hint
6. Game savestates, hint displays fullscreen, press any button to return

## Requirements

- **Batocera** v38+ (tested on v40 with Python 3.12)
- **Network connection** for API calls
- **API Key** from [Anthropic](https://console.anthropic.com/) or [OpenAI](https://platform.openai.com/)
- **SSH access** to your Batocera system

## Quick Install

### From Windows (PowerShell)

```powershell
# Clone the repo
git clone https://github.com/YOUR_USERNAME/ai-hint-bot.git
cd ai-hint-bot

# Deploy to Batocera (replace with your IP)
.\scripts\deploy.ps1 192.168.0.129
```

### From Windows (Command Prompt)

```batch
scripts\deploy.bat 192.168.0.129
```

### Manual Install

1. Copy files to Batocera via SCP:
```bash
scp -r src/* root@192.168.0.129:/userdata/system/ai-hints/
scp service/ai_hint root@192.168.0.129:/userdata/system/services/
```

2. SSH into Batocera:
```bash
ssh root@192.168.0.129
# Default password: linux
```

3. Set permissions:
```bash
chmod +x /userdata/system/ai-hints/daemon.py
chmod +x /userdata/system/services/ai_hint
```

## Configuration

### 1. Create your config file

Copy the example config:
```bash
cp /userdata/system/ai-hints/config.example.json /userdata/system/ai-hints/config.json
```

### 2. Add your API key (secure method)

Run the secure setup script:
```bash
/userdata/system/ai-hints/setup-api-key.sh
```

This prompts for your key (hidden input) and stores it in a secure `.secrets` file with restricted permissions. Your key is never stored in config.json.

**Alternative methods (in order of security):**

1. **Environment variable** (most secure):
   ```bash
   export ANTHROPIC_API_KEY="your-key-here"
   ```

2. **Secrets file** (secure - used by setup script):
   ```bash
   echo "API_KEY=your-key-here" > /userdata/system/ai-hints/.secrets
   chmod 600 /userdata/system/ai-hints/.secrets
   ```

3. ~~Config file~~ (not recommended - can be accidentally shared)

### 3. Configure your controller (if needed)

Find your controller device:
```bash
python3 -c "
import evdev
for path in evdev.list_devices():
    dev = evdev.InputDevice(path)
    print(f'{path}: {dev.name}')
"
```

Update `controller_device` in config.json if not `/dev/input/event0`.

## Starting the Service

```bash
# Start the service
batocera-services start ai_hint

# Check status
batocera-services status ai_hint

# View logs
tail -f /userdata/system/ai-hints/daemon.log

# Stop the service
batocera-services stop ai_hint
```

The service starts automatically on boot once installed.

## Testing

### Run component tests
```bash
/userdata/system/ai-hints/test-components.sh
```

### Manual trigger (without controller hotkeys)
```bash
# Request a hint (while game is running)
/userdata/system/ai-hints/trigger-hint.sh request

# View the hint
/userdata/system/ai-hints/trigger-hint.sh view
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `api_provider` | `"anthropic"` | `"anthropic"` or `"openai"` |
| `api_key` | `""` | Your API key |
| `model` | `"claude-sonnet-4-20250514"` | Model to use |
| `daily_limit` | `10` | Max API calls per day (0 = unlimited) |
| `hotkey_request` | `["BTN_SELECT", "BTN_TL"]` | Buttons to request hint |
| `hotkey_view` | `["BTN_SELECT", "BTN_TR"]` | Buttons to view hint |
| `controller_device` | `"/dev/input/event0"` | Controller input device |
| `savestate_slot` | `9` | Slot used for hint viewing |
| `hint_width` | `1280` | Hint image width |
| `hint_height` | `720` | Hint image height |

## Rate Limiting

The system enforces a daily API call limit to prevent runaway costs:

- Default limit: **10 calls per day**
- Resets at midnight (local time)
- Configurable via `daily_limit` in config.json
- Set to `0` for unlimited (not recommended)

When the limit is reached, you'll see "Daily limit reached! (10/10)" on screen.

Check current usage:
```bash
cat /userdata/system/ai-hints/usage_counter.json
```

## Logging

The system maintains detailed logs for debugging and usage tracking:

### Log Files

| File | Purpose |
|------|---------|
| `daemon.log` | Main log with all events, errors, timing |
| `usage.log` | JSON log of all hint requests for analytics |
| `usage_counter.json` | Daily counter for rate limiting |

### View Logs

```bash
# Live log stream
tail -f /userdata/system/ai-hints/daemon.log

# Recent usage
tail -20 /userdata/system/ai-hints/usage.log

# Pretty print usage log
cat /userdata/system/ai-hints/usage.log | python3 -m json.tool

# Check today's usage count
cat /userdata/system/ai-hints/usage_counter.json
```

### Log Levels

- **DEBUG** - Verbose internal details
- **INFO** - General information
- **EVENT** - User actions, API calls, important events
- **WARN** - Non-critical issues
- **ERROR** - Errors requiring attention

## Troubleshooting

### "No response from RetroArch"

Enable network commands in `/userdata/system/batocera.conf`:
```
global.retroarch.network_cmd_enable=true
global.retroarch.network_cmd_port=55355
```

Then reboot or restart the game.

### "evdev not available"

The daemon falls back to file-based triggers. Use the trigger script:
```bash
/userdata/system/ai-hints/trigger-hint.sh request
```

### "API Error 401"

Your API key is invalid. Double-check the key in config.json.

### "No hint ready"

- Make sure a game is running when you press the request hotkey
- Check the log: `tail /userdata/system/ai-hints/daemon.log`
- Wait for the "Hint Ready!" notification before pressing view hotkey

### Hint image not displaying

The daemon tries these display methods in order:
1. `fbi` (framebuffer image viewer)
2. `feh` (X11 image viewer)
3. RetroArch pause with message (fallback)

If none work, hints are saved to `/userdata/system/ai-hints/current-hint.png`.

## File Structure

```
/userdata/system/
├── services/
│   └── ai_hint              # Service script
└── ai-hints/
    ├── daemon.py            # Main daemon
    ├── config.json          # Your config (with API key)
    ├── config.example.json  # Template config
    ├── daemon.log           # Main log (events, errors, timing)
    ├── usage.log            # JSON usage log (analytics)
    ├── usage_counter.json   # Daily rate limit counter
    ├── current-hint.png     # Latest hint image
    └── archive/             # Saved hints
        └── [System]/
            └── [Game]/
                └── [timestamp].png
```

## Security Notes

- Never commit `config.json` with your API key
- The `.gitignore` excludes sensitive files
- Use `config.example.json` as a template
- API keys are stored locally on your Batocera system

## License

MIT License - See [LICENSE](LICENSE) file.
