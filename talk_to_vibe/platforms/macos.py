import subprocess
import time

from talk_to_vibe.platforms.base import BasePlatform, PasteResult
from talk_to_vibe.errors import PlatformError

_MODIFIER_KEYS = {"alt_r", "alt_l", "cmd_r", "cmd_l", "ctrl_r", "ctrl_l", "shift_r", "shift_l", "cmd", "ctrl", "alt", "shift"}


class MacOSPlatform(BasePlatform):
    def build_listener_kwargs(self, logger, ptt_chord: frozenset | None = None, debug_key_events: bool = False) -> dict:
        from Quartz import CGEventGetFlags, CGEventGetIntegerValueField, kCGKeyboardEventKeycode
        from pynput import keyboard as kb

        CTRL_MASK  = 0x040000
        SHIFT_MASK = 0x020000
        ALT_MASK   = 0x080000
        CMD_MASK   = 0x100000
        ALL_MOD    = CTRL_MASK | SHIFT_MASK | ALT_MASK | CMD_MASK

        suppress_vks: set[int] = set()
        required_flags = 0
        for key in (ptt_chord or ()):
            if key == kb.Key.ctrl:
                required_flags |= CTRL_MASK
            elif key == kb.Key.shift:
                required_flags |= SHIFT_MASK
            elif key == kb.Key.alt:
                required_flags |= ALT_MASK
            elif key == kb.Key.cmd:
                required_flags |= CMD_MASK
            elif isinstance(key, kb.KeyCode) and key.vk is not None:
                suppress_vks.add(key.vk)

        def intercept(event_type, event):
            vk = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event)
            if suppress_vks and vk in suppress_vks and (flags & ALL_MOD) == required_flags:
                return None
            if debug_key_events:
                logger.info("Quartz intercept event_type=%s vk=%s flags=%s", event_type, vk, flags)
            return event

        return {"darwin_intercept": intercept}

    def normalize_listener_key(self, key: object) -> object:
        from pynput import keyboard

        generic_map = {
            keyboard.Key.alt_l: keyboard.Key.alt,
            keyboard.Key.alt_r: keyboard.Key.alt,
            keyboard.Key.alt: keyboard.Key.alt,
            keyboard.Key.ctrl_l: keyboard.Key.ctrl,
            keyboard.Key.ctrl_r: keyboard.Key.ctrl,
            keyboard.Key.ctrl: keyboard.Key.ctrl,
            keyboard.Key.shift_l: keyboard.Key.shift,
            keyboard.Key.shift_r: keyboard.Key.shift,
            keyboard.Key.shift: keyboard.Key.shift,
            keyboard.Key.cmd_l: keyboard.Key.cmd,
            keyboard.Key.cmd_r: keyboard.Key.cmd,
            keyboard.Key.cmd: keyboard.Key.cmd,
        }
        if isinstance(key, keyboard.KeyCode) and key.vk is not None and not getattr(key, "_is_media", None):
            return keyboard.KeyCode.from_vk(key.vk)
        return generic_map.get(key, key)

    def describe_listener_key(self, key: object) -> str:
        normalized = self.normalize_listener_key(key)
        if normalized == key:
            return repr(key)
        return f"{key!r} -> {normalized!r}"

    def has_global_key_access(self) -> bool:
        return self.has_accessibility_access() and self.has_listen_event_access()

    def has_accessibility_access(self) -> bool:
        import objc

        app_services = objc.loadBundle(
            "ApplicationServices",
            globals(),
            "/System/Library/Frameworks/ApplicationServices.framework",
        )
        functions = {}
        objc.loadBundleFunctions(
            app_services,
            functions,
            [("AXIsProcessTrusted", b"Z")],
        )
        return bool(functions["AXIsProcessTrusted"]())

    def request_accessibility_access(self) -> bool:
        import objc

        app_services = objc.loadBundle(
            "ApplicationServices",
            globals(),
            "/System/Library/Frameworks/ApplicationServices.framework",
        )
        functions = {}
        objc.loadBundleFunctions(
            app_services,
            functions,
            [("AXIsProcessTrustedWithOptions", b"Z@")],
        )
        return bool(functions["AXIsProcessTrustedWithOptions"]({"AXTrustedCheckOptionPrompt": True}))

    def has_listen_event_access(self) -> bool:
        from Quartz import CGPreflightListenEventAccess

        return bool(CGPreflightListenEventAccess())

    def request_global_key_access(self) -> bool:
        from Quartz import CGRequestListenEventAccess

        listen_event_ok = bool(CGRequestListenEventAccess())
        accessibility_ok = self.request_accessibility_access()
        return listen_event_ok and accessibility_ok

    def get_global_key_access_status(self) -> dict[str, bool]:
        return {
            "accessibility": self.has_accessibility_access(),
            "listen_event": self.has_listen_event_access(),
        }

    def get_key_map(self) -> dict[str, object]:
        from pynput import keyboard
        return {
            "1": keyboard.KeyCode.from_vk(0x12),
            "2": keyboard.KeyCode.from_vk(0x13),
            "3": keyboard.KeyCode.from_vk(0x14),
            "4": keyboard.KeyCode.from_vk(0x15),
            "5": keyboard.KeyCode.from_vk(0x17),
            "6": keyboard.KeyCode.from_vk(0x16),
            "7": keyboard.KeyCode.from_vk(0x1A),
            "8": keyboard.KeyCode.from_vk(0x1C),
            "9": keyboard.KeyCode.from_vk(0x19),
            "0": keyboard.KeyCode.from_vk(0x1D),
            "f18": keyboard.KeyCode.from_vk(0x4F),
            "f19": keyboard.KeyCode.from_vk(0x50),
            "f20": keyboard.KeyCode.from_vk(0x5A),
            "f9": keyboard.Key.f9,
            "f10": keyboard.Key.f10,
            "f11": keyboard.Key.f11,
            "f12": keyboard.Key.f12,
            "alt_r": keyboard.Key.alt,
            "alt_l": keyboard.Key.alt,
            "alt": keyboard.Key.alt,
            "cmd_r": keyboard.Key.cmd,
            "cmd_l": keyboard.Key.cmd,
            "cmd": keyboard.Key.cmd,
            "ctrl_r": keyboard.Key.ctrl,
            "ctrl_l": keyboard.Key.ctrl,
            "ctrl": keyboard.Key.ctrl,
            "shift_r": keyboard.Key.shift,
            "shift_l": keyboard.Key.shift,
            "shift": keyboard.Key.shift,
        }

    def get_key_display_names(self) -> dict[str, str]:
        return {
            "1": "1",
            "2": "2",
            "3": "3",
            "4": "4",
            "5": "5",
            "6": "6",
            "7": "7",
            "8": "8",
            "9": "9",
            "0": "0",
            "f18": "F18",
            "f19": "F19",
            "f20": "F20",
            "f9": "F9",
            "f10": "F10",
            "f11": "F11",
            "f12": "F12",
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
        }

    def get_default_ptt_key(self) -> str:
        return "ctrl+9"

    def parse_ptt_chord(self, chord_str: str) -> frozenset:
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

    def paste_text(self, text: str, auto_enter: bool = False) -> PasteResult:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        kb.type(text)

        if auto_enter:
            time.sleep(0.05)
            kb.press(Key.enter)
            kb.release(Key.enter)
        return PasteResult(full_text=text)

    def play_success_sound(self) -> None:
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Pop.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def get_permission_help(self) -> list[str]:
        return self.get_global_key_permission_help() + self.get_microphone_permission_help()

    def get_global_key_permission_help(self) -> list[str]:
        return [
            "Input Monitoring or event access: System Settings -> Privacy & Security -> Input Monitoring",
            "Accessibility: System Settings -> Privacy & Security -> Accessibility",
        ]

    def get_microphone_permission_help(self) -> list[str]:
        return [
            "Microphone: System Settings → Privacy & Security → Microphone",
        ]
