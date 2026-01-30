#!/usr/bin/env python3
"""Detect controller button codes for config.json"""

import sys
import evdev

controller_path = sys.argv[1] if len(sys.argv) > 1 else "/dev/input/event24"

try:
    device = evdev.InputDevice(controller_path)
    print(f"Listening to: {device.name}")
    print()

    for event in device.read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.value == 1:
            # Find the name for this code
            name = None
            for code_name, code_val in evdev.ecodes.ecodes.items():
                if code_val == event.code and code_name.startswith(("BTN_", "KEY_")):
                    name = code_name
                    break

            if name:
                print(f"  {name}")
            else:
                print(f"  Unknown (code {event.code})")

except KeyboardInterrupt:
    print("\nDone.")
except Exception as e:
    print(f"Error: {e}")
