import subprocess
import time

from talk_to_vibe.platforms.base import BasePlatform
from talk_to_vibe.errors import PlatformError

_MODIFIER_KEYS = {"alt_r", "alt_l", "cmd_r", "cmd_l", "ctrl_r", "ctrl_l", "shift_r", "shift_l", "cmd", "ctrl", "alt", "shift"}


class MacOSPlatform(BasePlatform):
    def get_key_map(self) -> dict[str, object]:
        from pynput import keyboard
        return {
            "alt_r": keyboard.Key.alt_r,
            "alt_l": keyboard.Key.alt_l,
            "alt": keyboard.Key.alt_l,
            "cmd_r": keyboard.Key.cmd_r,
            "cmd_l": keyboard.Key.cmd_l,
            "cmd": keyboard.Key.cmd_l,
            "ctrl_r": keyboard.Key.ctrl_r,
            "ctrl_l": keyboard.Key.ctrl_l,
            "ctrl": keyboard.Key.ctrl_l,
            "shift_r": keyboard.Key.shift_r,
            "shift_l": keyboard.Key.shift_l,
            "shift": keyboard.Key.shift_l,
            "f18": keyboard.KeyCode.from_vk(0x4F),
            "f19": keyboard.KeyCode.from_vk(0x50),
            "f20": keyboard.KeyCode.from_vk(0x5A),
        }

    def get_key_display_names(self) -> dict[str, str]:
        return {
            "alt_r": "Right Option (⌥)",
            "alt_l": "Left Option (⌥)",
            "alt": "Option (⌥)",
            "cmd_r": "Right Command (⌘)",
            "cmd_l": "Left Command (⌘)",
            "cmd": "Command (⌘)",
            "ctrl_r": "Right Control (⌃)",
            "ctrl_l": "Left Control (⌃)",
            "ctrl": "Control (⌃)",
            "shift_r": "Right Shift (⇧)",
            "shift_l": "Left Shift (⇧)",
            "shift": "Shift (⇧)",
            "f18": "F18",
            "f19": "F19",
            "f20": "F20",
        }

    def get_default_ptt_key(self) -> str:
        return "alt_r"

    def parse_ptt_chord(self, chord_str: str) -> frozenset:
        from pynput import keyboard

        key_map = self.get_key_map()
        parts = [p.strip() for p in chord_str.split("+")]
        keys = set()
        for part in parts:
            if part not in key_map:
                raise PlatformError(f"Unknown key in chord: '{part}'. Available: {sorted(key_map.keys())}")
            keys.add(key_map[part])
        return frozenset(keys)

    def get_chord_display_name(self, chord_str: str) -> str:
        display_names = self.get_key_display_names()
        parts = [p.strip() for p in chord_str.split("+")]
        displayed = [display_names.get(p, p) for p in parts]
        return " + ".join(displayed)

    def is_modifier_only(self, chord_str: str) -> bool:
        parts = [p.strip() for p in chord_str.split("+")]
        return all(p in _MODIFIER_KEYS for p in parts)

    def paste_text(self, text: str, auto_enter: bool = False) -> None:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-8"))
        time.sleep(0.1)

        from pynput.keyboard import Controller, Key
        kb = Controller()
        kb.press(Key.cmd)
        kb.press("v")
        kb.release("v")
        kb.release(Key.cmd)

        if auto_enter:
            time.sleep(0.05)
            kb.press(Key.enter)
            kb.release(Key.enter)

    def play_success_sound(self) -> None:
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Pop.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def get_permission_help(self) -> list[str]:
        return [
            "Accessibility: System Settings → Privacy & Security → Accessibility",
            "Microphone: System Settings → Privacy & Security → Microphone",
        ]
