#!/usr/bin/env python3
"""
Batocera AI Hint System Daemon

A background service that provides on-demand AI-powered hints for retro games.
Player presses a hotkey, system captures screenshot, sends to Claude API,
and displays the hint on demand without interrupting gameplay.
"""

import socket
import json
import os
import sys
import time
import threading
import subprocess
import base64
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Optional imports - graceful fallback if not available
try:
    import evdev
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_CONFIG = {
    "api_provider": "anthropic",  # "anthropic" or "openai"
    "api_key": "",
    "model": "claude-sonnet-4-20250514",
    "daily_limit": 10,  # Maximum API calls per day (0 = unlimited)
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
    "prompt_template": """You are helping a player who is stuck in a retro video game.

System: {system}
Game: {game}

Based on the screenshot, provide a brief, spoiler-minimal hint about what to do next.
- Keep it to 2-3 sentences maximum
- Be specific to what's visible on screen
- Don't reveal major plot points or surprises
- Focus on the immediate obstacle or puzzle

Provide only the hint text, no preamble.""",
    "hint_font_size": 32,
    "hint_bg_color": [32, 32, 32],
    "hint_text_color": [255, 255, 255],
    "hint_width": 1280,
    "hint_height": 720,
    "debug": False
}


class Config:
    """Configuration manager with secure API key handling"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.secrets_path = self.config_path.parent / ".secrets"
        self.data = DEFAULT_CONFIG.copy()
        self.load()
        self._load_api_key()

    def load(self):
        """Load config from file, create default if not exists"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    self.data.update(user_config)
                log(f"Config loaded from {self.config_path}")
            except Exception as e:
                log(f"Error loading config: {e}", error=True)
        else:
            self.save()
            log(f"Created default config at {self.config_path}")

    def _load_api_key(self):
        """
        Load API key securely. Priority order:
        1. Environment variable (ANTHROPIC_API_KEY or OPENAI_API_KEY)
        2. Secrets file (.secrets in hints directory)
        3. Config file (least secure, not recommended)
        """
        provider = self.data.get("api_provider", "anthropic")

        # 1. Try environment variable first (most secure)
        env_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        env_key = os.environ.get(env_var)
        if env_key:
            self.data["api_key"] = env_key
            log(f"API key loaded from environment variable {env_var}")
            return

        # 2. Try secrets file (secure - restricted permissions)
        if self.secrets_path.exists():
            try:
                with open(self.secrets_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                if key.strip() == "API_KEY":
                                    self.data["api_key"] = value.strip()
                                    log(f"API key loaded from {self.secrets_path}")
                                    return
            except Exception as e:
                log(f"Error reading secrets file: {e}", error=True)

        # 3. Fall back to config file (not recommended)
        if self.data.get("api_key") and self.data["api_key"] != "YOUR_API_KEY_HERE":
            log("API key loaded from config.json (consider using .secrets file instead)", error=False)
        else:
            log("No API key found! Set ANTHROPIC_API_KEY env var or create .secrets file", error=True)

    def save(self):
        """Save current config to file (excludes API key for security)"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        # Don't save API key to config file
        save_data = {k: v for k, v in self.data.items() if k != "api_key"}
        save_data["api_key"] = ""  # Placeholder
        with open(self.config_path, 'w') as f:
            json.dump(save_data, f, indent=2)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key: str):
        return self.data[key]


# =============================================================================
# Logging
# =============================================================================

class Logger:
    """Enhanced logger with detailed tracking and multiple log levels"""

    LEVELS = {
        "DEBUG": 10,
        "INFO": 20,
        "EVENT": 25,  # User actions, API calls
        "WARN": 30,
        "ERROR": 40
    }

    def __init__(self, hints_dir: str, min_level: str = "DEBUG"):
        self.hints_dir = Path(hints_dir)
        self.hints_dir.mkdir(parents=True, exist_ok=True)

        self.log_file = self.hints_dir / "daemon.log"
        self.usage_log = self.hints_dir / "usage.log"
        self.min_level = self.LEVELS.get(min_level, 10)

        # Write startup header
        self._write_startup_header()

    def _write_startup_header(self):
        """Write a clear separator for new session"""
        separator = "=" * 70
        header = f"""
{separator}
  AI HINT SYSTEM - Session Started
  Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
  Python: {sys.version.split()[0]}
  evdev: {EVDEV_AVAILABLE}
  PIL: {PIL_AVAILABLE}
{separator}
"""
        with open(self.log_file, 'a') as f:
            f.write(header)

    def _format_message(self, level: str, message: str, **kwargs) -> str:
        """Format a log message with timestamp and metadata"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        base = f"[{timestamp}] [{level:5}] {message}"

        if kwargs:
            details = " | ".join(f"{k}={v}" for k, v in kwargs.items())
            base += f" | {details}"

        return base

    def _write(self, level: str, message: str, to_stderr: bool = False, **kwargs):
        """Write to log file"""
        if self.LEVELS.get(level, 0) < self.min_level:
            return

        line = self._format_message(level, message, **kwargs)

        try:
            with open(self.log_file, 'a') as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"Log write failed: {e}", file=sys.stderr)

        if to_stderr or level == "ERROR":
            print(line, file=sys.stderr)
        elif os.environ.get('DEBUG'):
            print(line)

    def debug(self, message: str, **kwargs):
        """Debug level - verbose details"""
        self._write("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs):
        """Info level - general information"""
        self._write("INFO", message, **kwargs)

    def event(self, message: str, **kwargs):
        """Event level - user actions, API calls, important events"""
        self._write("EVENT", message, **kwargs)

    def warn(self, message: str, **kwargs):
        """Warning level - non-critical issues"""
        self._write("WARN", message, **kwargs)

    def error(self, message: str, **kwargs):
        """Error level - errors that need attention"""
        self._write("ERROR", message, to_stderr=True, **kwargs)

    def log_usage(self, event_type: str, game: str, system: str,
                  success: bool, response_time: float = 0, hint_preview: str = "", **kwargs):
        """Log usage event to separate usage log for tracking"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date = datetime.now().strftime("%Y-%m-%d")

        entry = {
            "timestamp": timestamp,
            "date": date,
            "event": event_type,
            "game": game,
            "system": system,
            "success": success,
            "response_time_ms": int(response_time * 1000),
            "hint_preview": hint_preview[:100] if hint_preview else "",
            **kwargs
        }

        try:
            with open(self.usage_log, 'a') as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self.error(f"Usage log write failed: {e}")

        # Also write to main log
        self.event(
            f"USAGE: {event_type}",
            game=game,
            system=system,
            success=success,
            response_ms=int(response_time * 1000)
        )


# Global logger instance
_logger: Logger = None


def init_logging(hints_dir: str):
    """Initialize the global logger"""
    global _logger
    _logger = Logger(hints_dir)


def log(message: str, error: bool = False, **kwargs):
    """Compatibility wrapper for simple logging"""
    if _logger:
        if error:
            _logger.error(message, **kwargs)
        else:
            _logger.info(message, **kwargs)
    else:
        # Fallback before logger is initialized
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}", file=sys.stderr if error else sys.stdout)


def log_debug(message: str, **kwargs):
    """Log debug message"""
    if _logger:
        _logger.debug(message, **kwargs)


def log_event(message: str, **kwargs):
    """Log event message"""
    if _logger:
        _logger.event(message, **kwargs)


def log_usage(event_type: str, game: str, system: str, success: bool, **kwargs):
    """Log usage event"""
    if _logger:
        _logger.log_usage(event_type, game, system, success, **kwargs)


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """Track and enforce daily API usage limits"""

    def __init__(self, hints_dir: str, daily_limit: int = 10):
        self.hints_dir = Path(hints_dir)
        self.daily_limit = daily_limit
        self.usage_file = self.hints_dir / "usage_counter.json"
        self.usage_data = self._load()

    def _load(self) -> dict:
        """Load usage data from file"""
        if self.usage_file.exists():
            try:
                with open(self.usage_file, 'r') as f:
                    data = json.load(f)
                    log_debug(f"Loaded usage data: {data}")
                    return data
            except Exception as e:
                log(f"Error loading usage data: {e}", error=True)

        return {"date": "", "count": 0, "history": []}

    def _save(self):
        """Save usage data to file"""
        try:
            self.hints_dir.mkdir(parents=True, exist_ok=True)
            with open(self.usage_file, 'w') as f:
                json.dump(self.usage_data, f, indent=2)
        except Exception as e:
            log(f"Error saving usage data: {e}", error=True)

    def _get_today(self) -> str:
        """Get today's date string"""
        return datetime.now().strftime("%Y-%m-%d")

    def _reset_if_new_day(self):
        """Reset counter if it's a new day"""
        today = self._get_today()
        if self.usage_data.get("date") != today:
            # Save yesterday's count to history
            if self.usage_data.get("date") and self.usage_data.get("count", 0) > 0:
                history = self.usage_data.get("history", [])
                history.append({
                    "date": self.usage_data["date"],
                    "count": self.usage_data["count"]
                })
                # Keep last 30 days
                self.usage_data["history"] = history[-30:]

            # Reset for new day
            self.usage_data["date"] = today
            self.usage_data["count"] = 0
            self._save()
            log_event(f"New day - usage counter reset", date=today)

    def can_make_request(self) -> tuple:
        """
        Check if a request can be made.
        Returns (allowed: bool, used: int, limit: int)
        """
        if self.daily_limit <= 0:  # 0 = unlimited
            return (True, 0, 0)

        self._reset_if_new_day()
        used = self.usage_data.get("count", 0)
        return (used < self.daily_limit, used, self.daily_limit)

    def record_request(self, game: str = "", system: str = "", success: bool = True):
        """Record that a request was made"""
        self._reset_if_new_day()
        self.usage_data["count"] = self.usage_data.get("count", 0) + 1
        self._save()

        used = self.usage_data["count"]
        remaining = max(0, self.daily_limit - used) if self.daily_limit > 0 else -1

        log_event(
            f"API request recorded",
            used=used,
            limit=self.daily_limit,
            remaining=remaining,
            game=game,
            system=system,
            success=success
        )

    def get_usage_stats(self) -> dict:
        """Get current usage statistics"""
        self._reset_if_new_day()
        used = self.usage_data.get("count", 0)
        return {
            "date": self._get_today(),
            "used": used,
            "limit": self.daily_limit,
            "remaining": max(0, self.daily_limit - used) if self.daily_limit > 0 else -1,
            "history": self.usage_data.get("history", [])
        }


# =============================================================================
# RetroArch Commander
# =============================================================================

class RetroArchCommander:
    """Send commands to RetroArch via UDP network interface"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(2.0)

    def send(self, command: str) -> str:
        """Send command and return response if any"""
        try:
            self.socket.sendto(command.encode(), (self.host, self.port))

            # Some commands return data
            if command.startswith("GET_"):
                try:
                    data, _ = self.socket.recvfrom(4096)
                    return data.decode().strip()
                except socket.timeout:
                    return ""
            return "OK"
        except Exception as e:
            log(f"RetroArch command failed: {command} - {e}", error=True)
            return ""

    def get_status(self) -> dict:
        """Get current game status, returns dict with game info"""
        response = self.send("GET_STATUS")
        # Expected format: GET_STATUS PLAYING content_name,core_name
        # or: GET_STATUS PAUSED content_name,core_name
        # or: GET_STATUS CONTENTLESS

        result = {
            "playing": False,
            "paused": False,
            "content": "",
            "core": "",
            "raw": response
        }

        if not response:
            return result

        parts = response.split()
        if len(parts) >= 2:
            status = parts[1] if len(parts) > 1 else ""
            result["playing"] = status == "PLAYING"
            result["paused"] = status == "PAUSED"

            if len(parts) >= 3:
                content_info = " ".join(parts[2:])
                # Format is: core,content,crc32 (e.g., commodore_amiga,GameName,crc32=xxxx)
                if "," in content_info:
                    content_parts = content_info.split(",", 2)
                    result["core"] = content_parts[0]
                    result["content"] = content_parts[1] if len(content_parts) > 1 else ""
                    # crc32 is in content_parts[2] if present, but we don't need it
                else:
                    result["content"] = content_info

        return result

    def show_message(self, text: str):
        """Display on-screen notification"""
        # Note: Command is SHOW_MSG not SHOW_MESG (verified in reference)
        self.send(f"SHOW_MSG {text}")

    def screenshot(self):
        """Trigger screenshot capture"""
        self.send("SCREENSHOT")

    def save_state(self, slot: int = None):
        """Save state to specified slot"""
        if slot is not None:
            self.send(f"SAVE_STATE_SLOT {slot}")
        self.send("SAVE_STATE")

    def load_state(self, slot: int = None):
        """Load state from specified slot"""
        if slot is not None:
            self.send(f"LOAD_STATE_SLOT {slot}")
        self.send("LOAD_STATE")

    def pause(self):
        """Toggle pause"""
        self.send("PAUSE_TOGGLE")

    def quit(self):
        """Quit current content"""
        self.send("QUIT")


# =============================================================================
# Screenshot Manager
# =============================================================================

class ScreenshotManager:
    """Handle screenshot capture and retrieval"""

    def __init__(self, screenshot_dir: str, retroarch: RetroArchCommander):
        self.screenshot_dir = Path(screenshot_dir)
        self.retroarch = retroarch

    def capture(self) -> Path:
        """Capture screenshot and return path to file"""
        # Record time before capture
        before = time.time()

        # Trigger capture
        self.retroarch.screenshot()

        # Wait a moment for file to be written
        time.sleep(0.5)

        # Find the newest PNG in screenshot directory
        return self.find_latest(after_time=before - 1)

    def find_latest(self, after_time: float = 0) -> Path:
        """Find the most recent screenshot file"""
        if not self.screenshot_dir.exists():
            log(f"Screenshot directory not found: {self.screenshot_dir}", error=True)
            return None

        newest = None
        newest_time = after_time

        for png in self.screenshot_dir.glob("*.png"):
            mtime = png.stat().st_mtime
            if mtime > newest_time:
                newest_time = mtime
                newest = png

        return newest


# =============================================================================
# Game Info Parser
# =============================================================================

class GameInfoParser:
    """Extract system and game information from RetroArch status"""

    # Map core names to system names
    CORE_TO_SYSTEM = {
        "snes9x": "SNES",
        "bsnes": "SNES",
        "mesen-s": "SNES",
        "genesis_plus_gx": "Genesis",
        "picodrive": "Genesis",
        "blastem": "Genesis",
        "mgba": "GBA",
        "vba_next": "GBA",
        "gambatte": "Game Boy",
        "sameboy": "Game Boy",
        "nestopia": "NES",
        "mesen": "NES",
        "fceumm": "NES",
        "mupen64plus_next": "N64",
        "parallel_n64": "N64",
        "pcsx_rearmed": "PlayStation",
        "duckstation": "PlayStation",
        "swanstation": "PlayStation",
        "beetle_psx": "PlayStation",
        "flycast": "Dreamcast",
        "mednafen_saturn": "Saturn",
        "yabause": "Saturn",
        "stella": "Atari 2600",
        "prosystem": "Atari 7800",
        "mame": "Arcade",
        "fbneo": "Arcade",
        "dosbox_pure": "DOS",
        "scummvm": "ScummVM",
        # Amiga cores
        "puae": "Amiga",
        "commodore_amiga": "Amiga",
        "fsuae": "Amiga",
        # Commodore 64
        "vice": "C64",
        "vice_x64": "C64",
        # Other systems
        "hatari": "Atari ST",
        "px68k": "X68000",
        "quasi88": "PC-88",
        "np2kai": "PC-98",
    }

    @classmethod
    def parse(cls, status: dict) -> tuple:
        """
        Parse status dict and return (system, game) tuple.
        System is derived from core name, game from content name.
        """
        content = status.get("content", "Unknown Game")
        core = status.get("core", "").lower()

        # Clean up content name (remove path, extension)
        game = Path(content).stem if content else "Unknown Game"

        # Determine system from core
        system = "Unknown System"
        for core_name, system_name in cls.CORE_TO_SYSTEM.items():
            if core_name in core:
                system = system_name
                break

        return system, game


# =============================================================================
# AI API Caller
# =============================================================================

class AIClient:
    """Handle API calls to Claude or OpenAI"""

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config["api_key"]
        self.provider = config["api_provider"]
        self.model = config["model"]

    def get_hint(self, screenshot_path: Path, system: str, game: str) -> str:
        """Send screenshot to AI and get hint response"""
        if not self.api_key:
            return "Error: No API key configured. Edit config.json to add your API key."

        # Read and encode screenshot
        with open(screenshot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Build prompt
        prompt = self.config["prompt_template"].format(system=system, game=game)

        if self.provider == "anthropic":
            return self._call_anthropic(image_data, prompt)
        elif self.provider == "openai":
            return self._call_openai(image_data, prompt)
        else:
            return f"Error: Unknown API provider: {self.provider}"

    def _call_anthropic(self, image_b64: str, prompt: str) -> str:
        """Call Claude API"""
        url = "https://api.anthropic.com/v1/messages"

        payload = {
            "model": self.model,
            "max_tokens": 300,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))

                # Extract text from response
                if "content" in result and len(result["content"]) > 0:
                    return result["content"][0].get("text", "No hint generated.")
                return "No hint generated."

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            log(f"Anthropic API error: {e.code} - {error_body}", error=True)
            return f"API Error: {e.code}"
        except Exception as e:
            log(f"Anthropic API exception: {e}", error=True)
            return f"Error: {str(e)}"

    def _call_openai(self, image_b64: str, prompt: str) -> str:
        """Call OpenAI API"""
        url = "https://api.openai.com/v1/chat/completions"

        payload = {
            "model": self.model if "gpt" in self.model else "gpt-4o",
            "max_tokens": 300,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))

                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                return "No hint generated."

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            log(f"OpenAI API error: {e.code} - {error_body}", error=True)
            return f"API Error: {e.code}"
        except Exception as e:
            log(f"OpenAI API exception: {e}", error=True)
            return f"Error: {str(e)}"


# =============================================================================
# Hint Renderer
# =============================================================================

class HintRenderer:
    """Render hint text as an image"""

    def __init__(self, config: Config):
        self.config = config
        self.width = config["hint_width"]
        self.height = config["hint_height"]
        self.bg_color = tuple(config["hint_bg_color"])
        self.text_color = tuple(config["hint_text_color"])
        self.font_size = config["hint_font_size"]

    def render(self, hint_text: str, game: str, system: str) -> Path:
        """Render hint text to PNG image, return path"""
        hints_dir = Path(self.config["hints_dir"])
        output_path = hints_dir / "current-hint.png"
        text_path = hints_dir / "current-hint.txt"
        hints_dir.mkdir(parents=True, exist_ok=True)

        # Always save text version for OSD fallback display
        with open(text_path, 'w') as f:
            f.write(f"{system} - {game}\n\n{hint_text}")

        if PIL_AVAILABLE:
            result = self._render_pil(hint_text, game, system, output_path)
        else:
            result = self._render_fallback(hint_text, game, system, output_path)

        # Also save to screenshots folder as backup (viewable in Batocera GUI)
        try:
            screenshots_dir = Path(self.config["screenshot_dir"])
            if screenshots_dir.exists():
                import shutil
                safe_game = "".join(c if c.isalnum() or c in "._-" else "_" for c in game)[:30]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = screenshots_dir / f"HINT_{safe_game}_{timestamp}.png"
                shutil.copy2(output_path, backup_path)
                log(f"Hint backup saved to {backup_path}")
        except Exception as e:
            log_debug(f"Could not save hint backup: {e}")

        return result

    def _render_pil(self, hint_text: str, game: str, system: str, output_path: Path) -> Path:
        """Render using PIL/Pillow"""
        img = Image.new("RGB", (self.width, self.height), self.bg_color)
        draw = ImageDraw.Draw(img)

        # Try to load a font, fall back to default
        try:
            # Try common Linux font paths
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            ]
            font = None
            for fp in font_paths:
                if os.path.exists(fp):
                    font = ImageFont.truetype(fp, self.font_size)
                    break
            if font is None:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        # Draw header
        header = f"{system} - {game}"
        header_font_size = int(self.font_size * 0.8)
        try:
            header_font = ImageFont.truetype(font.path, header_font_size) if hasattr(font, 'path') else font
        except:
            header_font = font

        draw.text((40, 30), header, fill=(180, 180, 180), font=header_font)

        # Word wrap the hint text
        margin = 40
        max_width = self.width - (margin * 2)
        lines = self._wrap_text(hint_text, font, max_width, draw)

        # Draw hint text centered vertically
        line_height = self.font_size + 10
        total_height = len(lines) * line_height
        y_start = (self.height - total_height) // 2

        for i, line in enumerate(lines):
            y = y_start + (i * line_height)
            draw.text((margin, y), line, fill=self.text_color, font=font)

        # Draw footer instruction
        footer = "Press any button to return to game"
        footer_font_size = int(self.font_size * 0.6)
        try:
            footer_font = ImageFont.truetype(font.path, footer_font_size) if hasattr(font, 'path') else font
        except:
            footer_font = font
        draw.text((40, self.height - 50), footer, fill=(120, 120, 120), font=footer_font)

        img.save(output_path, "PNG")
        log(f"Hint image saved to {output_path}")
        return output_path

    def _wrap_text(self, text: str, font, max_width: int, draw) -> list:
        """Wrap text to fit within max_width"""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            try:
                bbox = draw.textbbox((0, 0), test_line, font=font)
                width = bbox[2] - bbox[0]
            except AttributeError:
                # Older PIL without textbbox
                width = draw.textsize(test_line, font=font)[0]

            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def _render_fallback(self, hint_text: str, game: str, system: str, output_path: Path) -> Path:
        """Render using ImageMagick convert command (fallback)"""
        # Create a simple text image using convert
        header = f"{system} - {game}"
        footer = "Press any button to return to game"

        # Escape text for shell
        def escape(s):
            return s.replace("'", "'\\''")

        cmd = [
            "convert",
            "-size", f"{self.width}x{self.height}",
            f"xc:rgb({self.bg_color[0]},{self.bg_color[1]},{self.bg_color[2]})",
            "-fill", f"rgb({self.text_color[0]},{self.text_color[1]},{self.text_color[2]})",
            "-font", "DejaVu-Sans",
            "-pointsize", str(self.font_size),
            "-gravity", "Center",
            "-annotate", "+0+0", hint_text,
            "-fill", "gray",
            "-pointsize", str(int(self.font_size * 0.6)),
            "-gravity", "North",
            "-annotate", "+0+30", header,
            "-gravity", "South",
            "-annotate", "+0+30", footer,
            str(output_path)
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            log(f"Hint image saved to {output_path} (ImageMagick)")
            return output_path
        except Exception as e:
            log(f"ImageMagick render failed: {e}", error=True)
            # Last resort: create a simple PPM and convert
            return self._render_ppm_fallback(hint_text, output_path)

    def _render_ppm_fallback(self, hint_text: str, output_path: Path) -> Path:
        """Absolute last resort: plain color image with text file"""
        # Just create a solid color PNG using pure Python
        # This is very basic but will work without any dependencies

        # Write hint text to a separate file for now
        text_path = output_path.with_suffix(".txt")
        with open(text_path, "w") as f:
            f.write(hint_text)

        log(f"PIL/ImageMagick unavailable. Hint text saved to {text_path}", error=True)
        return text_path


# =============================================================================
# Archive Manager
# =============================================================================

class ArchiveManager:
    """Manage hint archive storage"""

    def __init__(self, hints_dir: str):
        self.archive_dir = Path(hints_dir) / "archive"

    def save(self, hint_path: Path, system: str, game: str) -> Path:
        """Archive hint to system/game folder with timestamp"""
        # Clean names for filesystem
        safe_system = self._safe_name(system)
        safe_game = self._safe_name(game)

        dest_dir = self.archive_dir / safe_system / safe_game
        dest_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = dest_dir / f"{timestamp}.png"

        # Copy file
        import shutil
        shutil.copy2(hint_path, dest_path)

        log(f"Hint archived to {dest_path}")
        return dest_path

    def _safe_name(self, name: str) -> str:
        """Convert name to filesystem-safe string"""
        # Remove or replace unsafe characters
        unsafe = '<>:"/\\|?*'
        result = name
        for char in unsafe:
            result = result.replace(char, "_")
        return result[:50]  # Limit length


# =============================================================================
# Hint Viewer
# =============================================================================

class HintViewer:
    """Display hint image fullscreen"""

    def __init__(self, config: Config, retroarch: RetroArchCommander):
        self.config = config
        self.retroarch = retroarch
        self.display_method = None
        self._detect_display_method()

    def _detect_display_method(self):
        """Detect available display method"""
        # Check for direct framebuffer access (most reliable on KMS/DRM systems)
        # We use PIL to write directly to /dev/fb0, bypassing tools that can't get DRM master
        if PIL_AVAILABLE:
            try:
                # Check if framebuffer device exists and we can read its properties
                fb_size = Path('/sys/class/graphics/fb0/virtual_size')
                fb_bpp = Path('/sys/class/graphics/fb0/bits_per_pixel')
                if fb_size.exists() and fb_bpp.exists():
                    self.display_method = "direct_fb"
                    log("Display method: direct_fb (PIL + /dev/fb0)")
                    return
            except:
                pass

        # Check for mpv - works with KMS/DRM if it can get DRM master
        try:
            result = subprocess.run(["which", "mpv"], capture_output=True)
            if result.returncode == 0:
                self.display_method = "mpv"
                log("Display method: mpv (DRM output)")
                return
        except:
            pass

        # Check for fbv (framebuffer viewer) - fallback for non-KMS systems
        try:
            result = subprocess.run(["which", "fbv"], capture_output=True)
            if result.returncode == 0:
                self.display_method = "fbv"
                log("Display method: fbv (framebuffer viewer)")
                return
        except:
            pass

        # Check for fbi (framebuffer image viewer)
        try:
            result = subprocess.run(["which", "fbi"], capture_output=True)
            if result.returncode == 0:
                self.display_method = "fbi"
                log("Display method: fbi (framebuffer)")
                return
        except:
            pass

        # Check for feh
        try:
            result = subprocess.run(["which", "feh"], capture_output=True)
            if result.returncode == 0:
                self.display_method = "feh"
                log("Display method: feh")
                return
        except:
            pass

        # Fallback to RetroArch pause + message
        self.display_method = "retroarch_pause"
        log("Display method: retroarch_pause (fallback)")

    def show(self, hint_path: Path) -> bool:
        """
        Display hint image and wait for dismissal.
        Returns True when user dismisses the hint.
        """
        if self.display_method == "direct_fb":
            return self._show_direct_fb(hint_path)
        elif self.display_method == "fbv":
            return self._show_fbv(hint_path)
        elif self.display_method == "mpv":
            return self._show_mpv(hint_path)
        elif self.display_method == "fbi":
            return self._show_fbi(hint_path)
        elif self.display_method == "feh":
            return self._show_feh(hint_path)
        else:
            return self._show_retroarch_pause(hint_path)

    def _show_direct_fb(self, hint_path: Path) -> bool:
        """
        Write image directly to Linux framebuffer using PIL.
        This bypasses external tools and works on KMS/DRM systems by:
        1. Stopping RetroArch (freezes it but doesn't release DRM)
        2. Switching to text VT (triggers fbcon to take over display)
        3. Writing image directly to /dev/fb0
        4. Waiting for button press
        5. Switching back and resuming RetroArch
        """
        current_vt = None
        display_vt = None
        retroarch_suspended = False
        fb_data_backup = None

        try:
            log(f"Displaying hint with direct framebuffer: {hint_path}")

            # 1. Read framebuffer properties from sysfs
            try:
                with open('/sys/class/graphics/fb0/virtual_size', 'r') as f:
                    fb_size = f.read().strip()
                    fb_width, fb_height = map(int, fb_size.split(','))
                with open('/sys/class/graphics/fb0/bits_per_pixel', 'r') as f:
                    fb_bpp = int(f.read().strip())
                log_debug(f"Framebuffer: {fb_width}x{fb_height} @ {fb_bpp}bpp")
            except Exception as e:
                log(f"Could not read framebuffer properties: {e}", error=True)
                return self._show_retroarch_pause(hint_path)

            # 2. Get current VT
            try:
                result = subprocess.run(["fgconsole"], capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    current_vt = result.stdout.strip()
                    log_debug(f"Current VT: {current_vt}")
            except Exception as e:
                log_debug(f"Could not get current VT: {e}")

            # 3. Stop RetroArch
            try:
                subprocess.run(["pkill", "-STOP", "retroarch"], capture_output=True)
                retroarch_suspended = True
                log_debug("RetroArch suspended")
                time.sleep(0.3)
            except Exception as e:
                log_debug(f"Could not suspend RetroArch: {e}")

            # 4. Switch to a text VT to activate fbcon
            # This is crucial - fbcon takes over display when we switch to a text VT
            try:
                display_vt = "1" if current_vt != "1" else "3"
                subprocess.run(["chvt", display_vt], capture_output=True)
                log_debug(f"Switched to VT{display_vt}")
                time.sleep(0.5)  # Give fbcon time to take over
            except Exception as e:
                log_debug(f"Could not switch VT: {e}")

            # 5. Load and prepare image with PIL
            try:
                img = Image.open(hint_path)
                img = img.convert('RGB')  # Ensure RGB mode

                # Resize to fit framebuffer while maintaining aspect ratio
                img_ratio = img.width / img.height
                fb_ratio = fb_width / fb_height

                if img_ratio > fb_ratio:
                    # Image is wider - fit to width
                    new_width = fb_width
                    new_height = int(fb_width / img_ratio)
                else:
                    # Image is taller - fit to height
                    new_height = fb_height
                    new_width = int(fb_height * img_ratio)

                img = img.resize((new_width, new_height), Image.LANCZOS)

                # Create a black background and paste centered image
                canvas = Image.new('RGB', (fb_width, fb_height), (0, 0, 0))
                x_offset = (fb_width - new_width) // 2
                y_offset = (fb_height - new_height) // 2
                canvas.paste(img, (x_offset, y_offset))

                # Convert to framebuffer format
                if fb_bpp == 32:
                    # BGRA format (most common for 32bpp framebuffers)
                    canvas = canvas.convert('RGBA')
                    r, g, b, a = canvas.split()
                    canvas = Image.merge('RGBA', (b, g, r, a))
                    raw_data = canvas.tobytes()
                elif fb_bpp == 24:
                    # BGR format
                    r, g, b = canvas.split()
                    canvas = Image.merge('RGB', (b, g, r))
                    raw_data = canvas.tobytes()
                elif fb_bpp == 16:
                    # RGB565 format - need manual conversion
                    raw_data = self._convert_to_rgb565(canvas)
                else:
                    log(f"Unsupported framebuffer depth: {fb_bpp}bpp", error=True)
                    return self._show_retroarch_pause(hint_path)

                log_debug(f"Image prepared: {new_width}x{new_height}, {len(raw_data)} bytes")

            except Exception as e:
                log(f"Image preparation failed: {e}", error=True)
                return self._show_retroarch_pause(hint_path)

            # 6. Write to framebuffer
            try:
                with open('/dev/fb0', 'r+b') as fb:
                    # Optionally backup current framebuffer content
                    # fb_data_backup = fb.read(len(raw_data))
                    # fb.seek(0)
                    fb.write(raw_data)
                    fb.flush()
                log_debug("Image written to framebuffer")
            except PermissionError:
                log("Permission denied writing to /dev/fb0 - need root", error=True)
                return self._show_retroarch_pause(hint_path)
            except Exception as e:
                log(f"Framebuffer write failed: {e}", error=True)
                return self._show_retroarch_pause(hint_path)

            # 7. Wait for button press
            log_debug("Waiting for button press to dismiss hint...")
            if EVDEV_AVAILABLE:
                self._wait_for_button_press(timeout=300)
            else:
                time.sleep(10)  # Fallback: just wait 10 seconds

            log_debug("Button pressed, restoring display...")

            # 8. Switch back to original VT
            if current_vt:
                try:
                    subprocess.run(["chvt", current_vt], capture_output=True)
                    log_debug(f"Switched back to VT{current_vt}")
                    time.sleep(0.3)
                except Exception as e:
                    log_debug(f"Could not switch back to VT: {e}")

            # 9. Resume RetroArch
            if retroarch_suspended:
                subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
                log_debug("RetroArch resumed")

            return True

        except Exception as e:
            log(f"Direct framebuffer display failed: {e}", error=True)
            # Cleanup
            try:
                if current_vt:
                    subprocess.run(["chvt", current_vt], capture_output=True)
                if retroarch_suspended:
                    subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
            except:
                pass
            return self._show_retroarch_pause(hint_path)

    def _convert_to_rgb565(self, img: 'Image.Image') -> bytes:
        """Convert PIL Image to RGB565 format for 16bpp framebuffers"""
        import struct
        pixels = list(img.getdata())
        raw = []
        for r, g, b in pixels:
            # RGB565: 5 bits red, 6 bits green, 5 bits blue
            pixel = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            raw.append(struct.pack('<H', pixel))
        return b''.join(raw)

    def _show_fbv(self, hint_path: Path) -> bool:
        """Show using fbv framebuffer viewer with VT switching for KMS/DRM systems"""
        current_vt = None
        display_vt = None
        retroarch_suspended = False

        try:
            log(f"Displaying hint with fbv: {hint_path}")

            # 1. Get current virtual terminal
            try:
                result = subprocess.run(["fgconsole"], capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    current_vt = result.stdout.strip()
                    log_debug(f"Current VT: {current_vt}")
            except Exception as e:
                log_debug(f"Could not get current VT: {e}")

            # 2. Suspend RetroArch to stop it from rendering
            try:
                subprocess.run(["pkill", "-STOP", "retroarch"], capture_output=True)
                retroarch_suspended = True
                log_debug("RetroArch suspended")
                time.sleep(0.3)  # Give it time to stop
            except Exception as e:
                log_debug(f"Could not suspend RetroArch: {e}")

            # 3. Switch to a DIFFERENT VT for display
            # Batocera runs RetroArch on VT2, so we switch to VT1 for a clean framebuffer
            # If we're on VT1, switch to VT3. The key is switching AWAY from RetroArch's VT.
            try:
                if current_vt == "1":
                    display_vt = "3"
                else:
                    display_vt = "1"
                subprocess.run(["chvt", display_vt], capture_output=True)
                log_debug(f"Switched to VT{display_vt}")
                time.sleep(0.3)
            except Exception as e:
                log_debug(f"Could not switch VT: {e}")

            # 4. Clear the framebuffer and display image
            # fbv options: -f (fit to screen), -i (no info), -c (clear screen)
            process = subprocess.Popen(
                ["fbv", "-c", "-f", "-i", str(hint_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # 5. Wait for any controller input to dismiss
            if EVDEV_AVAILABLE:
                self._wait_for_button_press(timeout=300)
                process.terminate()
            else:
                # Without evdev, wait for process or timeout
                try:
                    process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    process.terminate()

            # 6. Switch back to original VT
            if current_vt:
                try:
                    subprocess.run(["chvt", current_vt], capture_output=True)
                    log_debug(f"Switched back to VT{current_vt}")
                except Exception as e:
                    log_debug(f"Could not switch back to VT: {e}")

            # 7. Resume RetroArch
            if retroarch_suspended:
                subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
                log_debug("RetroArch resumed")

            return True
        except FileNotFoundError:
            log("fbv not found, falling back", error=True)
            # Cleanup on error
            if retroarch_suspended:
                subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
            return self._show_retroarch_pause(hint_path)
        except Exception as e:
            log(f"fbv display failed: {e}", error=True)
            # Make sure to resume RetroArch and restore VT if we changed them
            try:
                if current_vt:
                    subprocess.run(["chvt", current_vt], capture_output=True)
                subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
            except:
                pass
            return self._show_retroarch_pause(hint_path)

    def _show_mpv(self, hint_path: Path) -> bool:
        """Show using mpv media player with DRM output (works with KMS systems like Batocera)"""
        retroarch_suspended = False

        try:
            log(f"Displaying hint with mpv: {hint_path}")

            # 1. Suspend RetroArch so mpv can take over DRM output
            try:
                subprocess.run(["pkill", "-STOP", "retroarch"], capture_output=True)
                retroarch_suspended = True
                log_debug("RetroArch suspended for mpv display")
                time.sleep(0.3)
            except Exception as e:
                log_debug(f"Could not suspend RetroArch: {e}")

            # 2. Run mpv with DRM output
            # mpv options for image display:
            # --vo=drm: use direct rendering manager (takes over display)
            # --image-display-duration=inf: keep image displayed
            # --really-quiet: suppress output
            # --no-osc: disable on-screen controller
            # --no-input-default-bindings: disable keyboard shortcuts
            log_debug("Starting mpv with DRM output...")
            process = subprocess.Popen(
                [
                    "mpv",
                    "--vo=drm",
                    "--image-display-duration=inf",
                    "--really-quiet",
                    "--no-osc",
                    "--no-input-default-bindings",
                    str(hint_path)
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Give mpv time to take over the display
            time.sleep(0.5)
            log_debug("Waiting for button press to dismiss hint...")

            # 3. Wait for any controller input to dismiss
            if EVDEV_AVAILABLE:
                self._wait_for_button_press(timeout=300)
                process.terminate()
                log_debug("Button pressed, terminating mpv")
            else:
                # Without evdev, wait for process or timeout
                try:
                    process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    process.terminate()

            # 4. Give mpv time to release DRM
            time.sleep(0.3)

            # 5. Resume RetroArch
            if retroarch_suspended:
                subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
                log_debug("RetroArch resumed")

            return True
        except FileNotFoundError:
            log("mpv not found, falling back", error=True)
            if retroarch_suspended:
                subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
            return self._show_retroarch_pause(hint_path)
        except Exception as e:
            log(f"mpv display failed: {e}", error=True)
            # Make sure to resume RetroArch
            try:
                subprocess.run(["pkill", "-CONT", "retroarch"], capture_output=True)
            except:
                pass
            return self._show_retroarch_pause(hint_path)

    def _wait_for_button_press(self, timeout: int = 300) -> bool:
        """Wait for any button press on the controller"""
        import select

        try:
            device_path = self.config["controller_device"]
            device = evdev.InputDevice(device_path)
            log_debug(f"Waiting for button press on {device.name}")

            start_time = time.time()
            while True:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    log_debug("Button wait timed out")
                    return False

                # Use select with remaining timeout
                remaining = timeout - elapsed
                r, w, x = select.select([device.fd], [], [], min(remaining, 1.0))

                if device.fd in r:
                    for event in device.read():
                        # Any key press (value=1 is press, value=0 is release)
                        if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                            log_debug(f"Button pressed: code={event.code}")
                            return True

        except Exception as e:
            log_debug(f"Button wait error: {e}")
            return False

    def _show_fbi(self, hint_path: Path) -> bool:
        """Show using framebuffer image viewer"""
        try:
            # fbi displays on framebuffer, press any key to exit
            subprocess.run(
                ["fbi", "-T", "1", "-a", "--noverbose", str(hint_path)],
                timeout=300  # 5 minute timeout
            )
            return True
        except subprocess.TimeoutExpired:
            subprocess.run(["killall", "fbi"], capture_output=True)
            return True
        except Exception as e:
            log(f"fbi display failed: {e}", error=True)
            return False

    def _show_feh(self, hint_path: Path) -> bool:
        """Show using feh image viewer"""
        try:
            subprocess.run(
                ["feh", "-F", "-Z", str(hint_path)],
                timeout=300
            )
            return True
        except subprocess.TimeoutExpired:
            subprocess.run(["killall", "feh"], capture_output=True)
            return True
        except Exception as e:
            log(f"feh display failed: {e}", error=True)
            return False

    def _show_retroarch_pause(self, hint_path: Path) -> bool:
        """
        Fallback: pause RetroArch and show hint text via OSD.
        Shows the hint text directly on screen.
        """
        # Read hint text from companion text file
        hint_text = ""
        text_path = hint_path.with_suffix(".txt")
        if text_path.exists():
            try:
                with open(text_path, "r") as f:
                    hint_text = f.read()
            except Exception as e:
                log(f"Error reading hint text: {e}", error=True)

        self.retroarch.pause()

        if hint_text:
            # Show hint text via OSD
            # RetroArch OSD can handle ~100-150 chars per message
            # Split into chunks and display with delays
            log(f"Displaying hint via OSD: {hint_text[:50]}...")

            # Clean up text for OSD (remove newlines, extra spaces)
            clean_text = " ".join(hint_text.split())

            # Split into chunks of ~120 chars at word boundaries
            chunks = []
            words = clean_text.split()
            current_chunk = ""
            for word in words:
                if len(current_chunk) + len(word) + 1 <= 120:
                    current_chunk += (" " + word if current_chunk else word)
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = word
            if current_chunk:
                chunks.append(current_chunk)

            # Display each chunk with a delay
            for i, chunk in enumerate(chunks):
                self.retroarch.show_message(chunk)
                time.sleep(4)  # Show each chunk for 4 seconds

            # Final message
            self.retroarch.show_message("Press Start to unpause and continue")
        else:
            self.retroarch.show_message("Hint ready - check ai-hints/current-hint.png")

        log("Hint displayed via RetroArch OSD")
        time.sleep(2)
        return True


# =============================================================================
# Hotkey Listener
# =============================================================================

class HotkeyListener:
    """Listen for controller hotkey combinations"""

    def __init__(self, config: Config, on_request: callable, on_view: callable):
        self.config = config
        self.on_request = on_request
        self.on_view = on_view
        self.running = False
        self.pressed_keys = set()

        self.request_combo = set(config["hotkey_request"])
        self.view_combo = set(config["hotkey_view"])
        self.device_path = config["controller_device"]

    def start(self):
        """Start listening in a thread"""
        self.running = True

        if EVDEV_AVAILABLE:
            thread = threading.Thread(target=self._listen_evdev, daemon=True)
        else:
            thread = threading.Thread(target=self._listen_fallback, daemon=True)

        thread.start()
        log("Hotkey listener started")

    def stop(self):
        """Stop listening"""
        self.running = False

    def _listen_evdev(self):
        """Listen using evdev library"""
        try:
            device = evdev.InputDevice(self.device_path)
            log(f"Listening on device: {device.name}")

            # Build button name to code mapping
            btn_codes = {}
            for name in list(self.request_combo) + list(self.view_combo):
                if hasattr(evdev.ecodes, name):
                    btn_codes[name] = getattr(evdev.ecodes, name)

            for event in device.read_loop():
                if not self.running:
                    break

                if event.type == evdev.ecodes.EV_KEY:
                    # Find button name from code
                    btn_name = None
                    for name, code in btn_codes.items():
                        if code == event.code:
                            btn_name = name
                            break

                    if btn_name:
                        if event.value == 1:  # Press
                            self.pressed_keys.add(btn_name)
                        elif event.value == 0:  # Release
                            self.pressed_keys.discard(btn_name)

                        # Check combos
                        self._check_combos()

        except Exception as e:
            log(f"evdev listener error: {e}", error=True)
            self._listen_fallback()

    def _listen_fallback(self):
        """Fallback: poll for input file or use alternative method"""
        log("Using fallback hotkey detection (file-based trigger)")

        # Watch for trigger files
        trigger_dir = Path(self.config["hints_dir"])
        request_trigger = trigger_dir / ".request_hint"
        view_trigger = trigger_dir / ".view_hint"

        while self.running:
            try:
                if request_trigger.exists():
                    request_trigger.unlink()
                    log("Request trigger detected")
                    self.on_request()

                if view_trigger.exists():
                    view_trigger.unlink()
                    log("View trigger detected")
                    self.on_view()

                time.sleep(0.2)
            except Exception as e:
                log(f"Fallback listener error: {e}", error=True)
                time.sleep(1)

    def _check_combos(self):
        """Check if any hotkey combo is currently pressed"""
        if self.request_combo.issubset(self.pressed_keys):
            log("Request hotkey detected")
            # Clear to prevent repeat triggers
            self.pressed_keys.clear()
            # Run callback in thread to not block listener
            threading.Thread(target=self.on_request, daemon=True).start()

        elif self.view_combo.issubset(self.pressed_keys):
            log("View hotkey detected")
            self.pressed_keys.clear()
            threading.Thread(target=self.on_view, daemon=True).start()


# =============================================================================
# Hint System (Main Coordinator)
# =============================================================================

class HintSystem:
    """Main coordinator for the AI hint system"""

    def __init__(self, config_path: str):
        self.config = Config(config_path)
        init_logging(self.config["hints_dir"])

        log_event("HintSystem initializing", config_path=config_path)

        self.retroarch = RetroArchCommander(
            self.config["retroarch_host"],
            self.config["retroarch_port"]
        )
        log_debug(f"RetroArch commander ready",
                  host=self.config["retroarch_host"],
                  port=self.config["retroarch_port"])

        self.screenshots = ScreenshotManager(
            self.config["screenshot_dir"],
            self.retroarch
        )
        log_debug(f"Screenshot manager ready", dir=self.config["screenshot_dir"])

        self.ai_client = AIClient(self.config)
        log_debug(f"AI client ready",
                  provider=self.config["api_provider"],
                  model=self.config["model"])

        self.rate_limiter = RateLimiter(
            self.config["hints_dir"],
            self.config["daily_limit"]
        )
        stats = self.rate_limiter.get_usage_stats()
        log_event(f"Rate limiter ready",
                  daily_limit=self.config["daily_limit"],
                  used_today=stats["used"],
                  remaining=stats["remaining"])

        self.renderer = HintRenderer(self.config)
        self.archive = ArchiveManager(self.config["hints_dir"])
        self.viewer = HintViewer(self.config, self.retroarch)
        self.hotkeys = HotkeyListener(
            self.config,
            self.on_request_hint,
            self.on_view_hint
        )

        self.hint_ready = False
        self.current_hint_path = None
        self.processing = False

        log_event("HintSystem initialized successfully")

    def run(self):
        """Start the hint system"""
        log("Starting AI Hint System daemon")
        self.hotkeys.start()

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log("Shutdown requested")
            self.hotkeys.stop()

    def on_request_hint(self):
        """Called when user presses the request hotkey"""
        log_event("Hint request hotkey pressed")

        if self.processing:
            log("Already processing a hint request")
            self.retroarch.show_message("Already generating hint...")
            return

        # Check rate limit before doing anything else
        allowed, used, limit = self.rate_limiter.can_make_request()
        if not allowed:
            log_event("Rate limit reached", used=used, limit=limit)
            msg = self.config["notification_limit_reached"].format(used=used, limit=limit)
            self.retroarch.show_message(msg)
            log_usage("RATE_LIMITED", "", "", success=False, used=used, limit=limit)
            return

        log_event("Hint request accepted", remaining=limit - used - 1)
        self.processing = True
        self.hint_ready = False

        # Get game status
        log_debug("Getting RetroArch status...")
        status = self.retroarch.get_status()
        log_debug(f"RetroArch status received", raw=status.get("raw", "")[:100])

        if not status["playing"] and not status["paused"]:
            log("No game running")
            self.retroarch.show_message("No game running!")
            self.processing = False
            return

        # Notify user
        self.retroarch.show_message(self.config["notification_generating"])

        # Capture screenshot
        log_debug("Capturing screenshot...")
        screenshot = self.screenshots.capture()
        if not screenshot:
            log("Screenshot capture failed", error=True)
            self.retroarch.show_message(self.config["notification_error"])
            self.processing = False
            return
        log_debug(f"Screenshot captured", path=str(screenshot))

        # Parse game info
        system, game = GameInfoParser.parse(status)
        log_event(f"Processing hint request", game=game, system=system)

        # Process in background
        threading.Thread(
            target=self._process_hint_request,
            args=(screenshot, system, game),
            daemon=True
        ).start()

    def _process_hint_request(self, screenshot: Path, system: str, game: str):
        """Background processing of hint request"""
        start_time = time.time()

        try:
            # Call AI API
            log_event("Calling AI API...", provider=self.config["api_provider"], model=self.config["model"])
            api_start = time.time()
            hint_text = self.ai_client.get_hint(screenshot, system, game)
            api_time = time.time() - api_start

            # Check if it was an error response
            is_error = hint_text.startswith("Error:") or hint_text.startswith("API Error:")
            if is_error:
                log(f"API returned error: {hint_text}", error=True)
                self.retroarch.show_message(self.config["notification_error"])
                log_usage("API_ERROR", game, system, success=False,
                         response_time=api_time, hint_preview=hint_text)
                self.processing = False
                return

            log_event(f"AI response received",
                     response_time_ms=int(api_time * 1000),
                     hint_length=len(hint_text))
            log_debug(f"Hint text: {hint_text[:200]}...")

            # Record successful API call
            self.rate_limiter.record_request(game, system, success=True)

            # Render hint image
            log_debug("Rendering hint image...")
            render_start = time.time()
            hint_path = self.renderer.render(hint_text, game, system)
            render_time = time.time() - render_start
            log_debug(f"Hint rendered", render_time_ms=int(render_time * 1000))

            # Archive
            archive_path = self.archive.save(hint_path, system, game)
            log_debug(f"Hint archived", path=str(archive_path))

            # Mark ready
            self.current_hint_path = hint_path
            self.hint_ready = True
            self.processing = False

            total_time = time.time() - start_time

            # Log usage
            log_usage("HINT_GENERATED", game, system, success=True,
                     response_time=api_time, hint_preview=hint_text,
                     total_time_ms=int(total_time * 1000))

            # Notify user
            self.retroarch.show_message(self.config["notification_ready"])
            log_event("Hint ready for viewing",
                     total_time_ms=int(total_time * 1000),
                     api_time_ms=int(api_time * 1000))

            # Log current usage stats
            stats = self.rate_limiter.get_usage_stats()
            log_event("Usage update",
                     used_today=stats["used"],
                     remaining=stats["remaining"],
                     limit=stats["limit"])

        except Exception as e:
            elapsed = time.time() - start_time
            log(f"Hint processing error: {e}", error=True)
            log_usage("PROCESSING_ERROR", game, system, success=False,
                     error=str(e), elapsed_ms=int(elapsed * 1000))
            self.retroarch.show_message(self.config["notification_error"])
            self.processing = False

    def on_view_hint(self):
        """Called when user presses the view hotkey"""
        log_event("View hint hotkey pressed")

        if not self.hint_ready or not self.current_hint_path:
            log("No hint ready to view")
            self.retroarch.show_message("No hint ready! Press Select+L1 first.")
            return

        log_event("Viewing hint", hint_path=str(self.current_hint_path))
        slot = self.config["savestate_slot"]
        view_start = time.time()

        # Save current state (wait longer for large save states like CD32/Amiga)
        log_debug(f"Saving state to slot {slot}...")
        self.retroarch.save_state(slot)
        time.sleep(2.0)  # Give time for save to complete before suspending RetroArch

        # Display hint
        log_debug("Displaying hint image...")
        display_start = time.time()
        self.viewer.show(self.current_hint_path)
        display_time = time.time() - display_start
        log_debug(f"Hint displayed", display_time_ms=int(display_time * 1000))

        # Restore state
        log_debug(f"Restoring state from slot {slot}...")
        time.sleep(0.2)
        self.retroarch.load_state(slot)

        total_time = time.time() - view_start
        log_event("Hint viewing complete",
                 total_time_ms=int(total_time * 1000),
                 display_time_ms=int(display_time * 1000))


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point"""
    # Default config location
    config_path = os.environ.get(
        "AIHINT_CONFIG",
        "/userdata/system/ai-hints/config.json"
    )

    # Allow override via command line
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    print("=" * 50)
    print("  AI Hint System")
    print("=" * 50)
    print(f"Config: {config_path}")
    print(f"evdev available: {EVDEV_AVAILABLE}")
    print(f"PIL available: {PIL_AVAILABLE}")
    print()

    hint_system = HintSystem(config_path)

    # Show rate limit status
    stats = hint_system.rate_limiter.get_usage_stats()
    print(f"Daily API Limit: {stats['limit']} calls")
    print(f"Used today: {stats['used']}")
    print(f"Remaining: {stats['remaining']}")
    print()
    print("Hotkeys:")
    print(f"  Request hint: {hint_system.config['hotkey_request']}")
    print(f"  View hint: {hint_system.config['hotkey_view']}")
    print()
    print("Logs:")
    print(f"  Main log: {hint_system.config['hints_dir']}/daemon.log")
    print(f"  Usage log: {hint_system.config['hints_dir']}/usage.log")
    print("=" * 50)
    print()

    hint_system.run()


if __name__ == "__main__":
    main()
