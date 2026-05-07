import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Iterable

from talk_to_vibe.platforms.base import BasePlatform, PasteResult
from talk_to_vibe.errors import PlatformError

_MODIFIER_KEYS = {
    "alt_r", "alt_l", "alt",
    "ctrl_r", "ctrl_l", "ctrl",
    "shift_r", "shift_l", "shift",
    "super_r", "super_l", "super",
    "cmd_r", "cmd_l", "cmd",
}

_CLIPBOARD_TOOLS = (
    ("xclip", ["xclip", "-selection", "clipboard"]),
    ("xsel", ["xsel", "--clipboard", "--input"]),
    ("wl-copy", ["wl-copy"]),
)

# WM_CLASS values (lowercased) for terminal emulators where Ctrl+Shift+V
# atomic clipboard paste is more reliable than per-character key injection.
# xdotool type into TUIs (Claude Code, vim, etc.) intermittently drops space
# characters; clipboard paste avoids the per-character timing entirely.
_TERMINAL_WINDOW_CLASSES = frozenset({
    "alacritty",
    "eterm",
    "foot",
    "gnome-terminal",
    "gnome-terminal-server",
    "kgx",
    "kitty",
    "konsole",
    "lxterminal",
    "mate-terminal",
    "org.wezfurlong.wezterm",
    "rxvt",
    "rxvt-unicode",
    "sakura",
    "st-256color",
    "terminator",
    "tilix",
    "urxvt",
    "wezterm",
    "xfce4-terminal",
    "xterm",
})

_WM_CLASS_RE = re.compile(r'"([^"]*)"')

_SOUND_PLAYERS = (
    ("canberra-gtk-play", ["canberra-gtk-play", "-i", "complete"]),
    ("paplay", ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"]),
    ("aplay", ["aplay", "-q", "/usr/share/sounds/alsa/Front_Center.wav"]),
)

_RESTORE_DELAY_SECONDS = 0.08


@dataclass(slots=True)
class _ClipboardSession:
    previous_text: str | None = None
    used_clipboard: bool = False
    last_written_text: str = ""
    restore_failed: bool = False
    restore_reason: str = ""


def _is_wayland() -> bool:
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class LinuxPlatform(BasePlatform):
    def _normalized_key_name(self, key_name: str) -> str:
        return {
            "alt_l": "alt",
            "alt_r": "alt",
            "ctrl_l": "ctrl",
            "ctrl_r": "ctrl",
            "shift_l": "shift",
            "shift_r": "shift",
            "super_l": "super",
            "super_r": "super",
            "cmd_l": "cmd",
            "cmd_r": "cmd",
        }.get(key_name, key_name)

    def get_key_map(self) -> dict[str, object]:
        from pynput import keyboard

        key_map: dict[str, object] = {
            "0": keyboard.KeyCode.from_char("0"),
            "1": keyboard.KeyCode.from_char("1"),
            "2": keyboard.KeyCode.from_char("2"),
            "3": keyboard.KeyCode.from_char("3"),
            "4": keyboard.KeyCode.from_char("4"),
            "5": keyboard.KeyCode.from_char("5"),
            "6": keyboard.KeyCode.from_char("6"),
            "7": keyboard.KeyCode.from_char("7"),
            "8": keyboard.KeyCode.from_char("8"),
            "9": keyboard.KeyCode.from_char("9"),
            "alt": keyboard.Key.alt,
            "alt_l": keyboard.Key.alt_l,
            "alt_r": keyboard.Key.alt_r,
            "ctrl": keyboard.Key.ctrl,
            "ctrl_l": keyboard.Key.ctrl_l,
            "ctrl_r": keyboard.Key.ctrl_r,
            "shift": keyboard.Key.shift,
            "shift_l": keyboard.Key.shift_l,
            "shift_r": keyboard.Key.shift_r,
            "super": keyboard.Key.cmd,
            "super_l": keyboard.Key.cmd_l,
            "super_r": keyboard.Key.cmd_r,
            "cmd": keyboard.Key.cmd,
            "cmd_l": keyboard.Key.cmd_l,
            "cmd_r": keyboard.Key.cmd_r,
        }
        for n in range(1, 13):
            key_map[f"f{n}"] = getattr(keyboard.Key, f"f{n}")
        for n in (13, 14, 15, 16, 17, 18, 19, 20):
            attr = getattr(keyboard.Key, f"f{n}", None)
            if attr is not None:
                key_map[f"f{n}"] = attr
        return key_map

    def get_key_display_names(self) -> dict[str, str]:
        names = {
            "0": "0",
            "1": "1",
            "2": "2",
            "3": "3",
            "4": "4",
            "5": "5",
            "6": "6",
            "7": "7",
            "8": "8",
            "9": "9",
            "alt": "Alt",
            "alt_l": "Left Alt",
            "alt_r": "Right Alt",
            "ctrl": "Ctrl",
            "ctrl_l": "Left Ctrl",
            "ctrl_r": "Right Ctrl",
            "shift": "Shift",
            "shift_l": "Left Shift",
            "shift_r": "Right Shift",
            "super": "Super",
            "super_l": "Left Super",
            "super_r": "Right Super",
            "cmd": "Super",
            "cmd_l": "Left Super",
            "cmd_r": "Right Super",
        }
        for n in range(1, 21):
            names[f"f{n}"] = f"F{n}"
        return names

    def get_default_ptt_key(self) -> str:
        return "ctrl+9"

    def parse_ptt_chord(self, chord_str: str) -> frozenset:
        key_map = self.get_key_map()
        parts = [p.strip() for p in chord_str.split("+") if p.strip()]
        if not parts:
            raise PlatformError(f"Empty chord: '{chord_str}'")
        keys = set()
        for part in parts:
            normalized_part = self._normalized_key_name(part)
            if normalized_part not in key_map:
                raise PlatformError(f"Unknown key in chord: '{part}'. Available: {sorted(key_map.keys())}")
            keys.add(key_map[normalized_part])
        return frozenset(keys)

    def get_chord_display_name(self, chord_str: str) -> str:
        display_names = self.get_key_display_names()
        parts = [p.strip() for p in chord_str.split("+") if p.strip()]
        return " + ".join(display_names.get(p, p) for p in parts)

    def is_modifier_only(self, chord_str: str) -> bool:
        parts = [p.strip() for p in chord_str.split("+") if p.strip()]
        if not parts:
            return False
        return all(p in _MODIFIER_KEYS for p in parts)

    def normalize_listener_key(self, key: object) -> object:
        from pynput import keyboard

        side_to_generic = {
            keyboard.Key.alt_l: keyboard.Key.alt,
            keyboard.Key.alt_r: keyboard.Key.alt,
            keyboard.Key.ctrl_l: keyboard.Key.ctrl,
            keyboard.Key.ctrl_r: keyboard.Key.ctrl,
            keyboard.Key.shift_l: keyboard.Key.shift,
            keyboard.Key.shift_r: keyboard.Key.shift,
            keyboard.Key.cmd_l: keyboard.Key.cmd,
            keyboard.Key.cmd_r: keyboard.Key.cmd,
        }
        return side_to_generic.get(key, key)

    def describe_listener_key(self, key: object) -> str:
        normalized = self.normalize_listener_key(key)
        if normalized == key:
            return repr(key)
        return f"{key!r} -> {normalized!r}"

    def paste_text(self, text: str, auto_enter: bool = False) -> PasteResult:
        if not text:
            return PasteResult(full_text="")
        return self.paste_text_stream([text], auto_enter=auto_enter)

    def paste_text_stream(self, chunks: Iterable[str], auto_enter: bool = False) -> PasteResult:
        # Decide the strategy once per utterance so it can't flip mid-paste if
        # focus briefly shifts. TUIs (Claude Code, vim, terminal apps) get an
        # atomic clipboard paste because xdotool's per-character key injection
        # drops characters (especially spaces) under their input load.
        # GUI apps get xdotool type, which works identically across editors,
        # browsers, and chat apps and does not depend on a paste shortcut.
        via_clipboard_paste = self._active_window_is_terminal()
        clipboard_session = self._begin_clipboard_session(via_clipboard_paste)
        parts: list[str] = []
        first = True
        for chunk in chunks:
            piece = chunk.strip() if chunk else ""
            if not piece:
                continue
            to_send = piece if first else " " + piece
            first = False
            parts.append(piece)
            self._paste_chunk(to_send, via_clipboard_paste, clipboard_session)

        full_text = " ".join(parts).strip()
        self._finish_clipboard_session(clipboard_session)
        if auto_enter and full_text:
            self._press_enter()
        return PasteResult(
            full_text=full_text,
            clipboard_restore_failed=clipboard_session.restore_failed,
            clipboard_restore_reason=clipboard_session.restore_reason,
        )

    def _begin_clipboard_session(self, via_clipboard_paste: bool) -> _ClipboardSession:
        if not via_clipboard_paste:
            return _ClipboardSession()
        return _ClipboardSession(previous_text=self._read_clipboard_text())

    def _finish_clipboard_session(self, session: _ClipboardSession) -> None:
        if not session.used_clipboard or session.previous_text is None:
            return
        time.sleep(_RESTORE_DELAY_SECONDS)
        restored, reason = self._restore_clipboard_text(
            previous_text=session.previous_text,
            expected_current_text=session.last_written_text,
        )
        if restored:
            return
        if reason == "clipboard changed":
            return
        session.restore_failed = True
        session.restore_reason = reason

    def _paste_chunk(self, text: str, via_clipboard_paste: bool, clipboard_session: _ClipboardSession) -> None:
        if via_clipboard_paste and self._paste_chunk_via_clipboard(text, clipboard_session):
            return
        if self._type_text_via_xdotool(text):
            return
        self._type_text_via_pynput(text)

    def _paste_chunk_via_clipboard(self, text: str, clipboard_session: _ClipboardSession) -> bool:
        if shutil.which("xdotool") is None:
            return False
        if not self._populate_clipboard(text):
            return False
        clipboard_session.used_clipboard = True
        clipboard_session.last_written_text = text
        # Brief pause so the X server registers the new selection before the
        # paste shortcut is fired.
        time.sleep(0.03)
        try:
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5.0,
            )
        except Exception:
            return False
        return True

    def _type_text_via_xdotool(self, text: str) -> bool:
        if shutil.which("xdotool") is None:
            return False
        try:
            # --delay 12 matches xdotool's documented safe default and clears
            # any modifiers the user may still have down (e.g. Ctrl from the
            # PTT chord) before injection.
            subprocess.run(
                ["xdotool", "type", "--delay", "12", "--clearmodifiers", "--", text],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30.0,
            )
        except Exception:
            return False
        return True

    def _type_text_via_pynput(self, text: str) -> None:
        from pynput.keyboard import Controller
        Controller().type(text)

    def _press_enter(self) -> None:
        time.sleep(0.05)
        if shutil.which("xdotool") is not None:
            try:
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", "Return"],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0,
                )
                return
            except Exception:
                pass
        try:
            from pynput.keyboard import Controller, Key
            kb = Controller()
            kb.press(Key.enter)
            kb.release(Key.enter)
        except Exception:
            pass

    def _read_clipboard_text(self) -> str | None:
        tool_name, command = self._select_clipboard_tool(output=True)
        if not tool_name:
            return None
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=2.0,
            )
        except Exception:
            return None
        if isinstance(result.stdout, bytes):
            try:
                return result.stdout.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if isinstance(result.stdout, str):
            return result.stdout
        return None

    def _restore_clipboard_text(self, previous_text: str, expected_current_text: str) -> tuple[bool, str]:
        current_text = self._read_clipboard_text()
        if current_text is None:
            return False, "could not read clipboard"
        if current_text != expected_current_text:
            return False, "clipboard changed"
        if self._populate_clipboard(previous_text):
            return True, ""
        return False, "could not restore clipboard"

    def _populate_clipboard(self, text: str) -> bool:
        tool_name, command = self._select_clipboard_tool(output=False)
        if not tool_name:
            return False
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE)
            process.communicate(text.encode("utf-8"), timeout=2.0)
            return True
        except Exception:
            return False

    def _active_window_is_terminal(self) -> bool:
        # Used to decide whether to paste via Ctrl+Shift+V (TUIs) or xdotool
        # type (GUIs). Defaults to False on any failure so we keep the
        # universally-compatible typing path.
        if shutil.which("xdotool") is None or shutil.which("xprop") is None:
            return False
        try:
            wid_result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=2.0,
            )
            wid = (wid_result.stdout or "").strip()
            if not wid or not wid.lstrip("-").isdigit():
                return False
            cls_result = subprocess.run(
                ["xprop", "-id", wid, "WM_CLASS"],
                capture_output=True, text=True, timeout=2.0,
            )
            stdout = cls_result.stdout or ""
            names = [m.lower() for m in _WM_CLASS_RE.findall(stdout)]
            return any(name in _TERMINAL_WINDOW_CLASSES for name in names)
        except Exception:
            return False

    def _select_clipboard_tool(self, output: bool = False) -> tuple[str | None, list[str] | None]:
        for name, command in _CLIPBOARD_TOOLS:
            if shutil.which(name) is not None:
                if output:
                    if name == "xclip":
                        return name, [*command, "-o"]
                    if name == "xsel":
                        return name, ["xsel", "--clipboard", "--output"]
                    if name == "wl-copy":
                        return None, None
                return name, command
        return None, None

    def play_success_sound(self) -> None:
        for name, command in _SOUND_PLAYERS:
            if shutil.which(name) is not None:
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

    def get_permission_help(self) -> list[str]:
        lines = [
            "Microphone: ensure the user is in the 'audio' group and PulseAudio/PipeWire is running.",
            "Clipboard: install xclip (or xsel) — apt install xclip",
        ]
        if _is_wayland():
            lines.append(
                "Wayland detected — global hotkeys via pynput do not work on Wayland. "
                "Log out and choose a Cinnamon (X11) session."
            )
        return lines

    def get_global_key_permission_help(self) -> list[str]:
        if _is_wayland():
            return [
                "Wayland session detected. TalkToVibe requires X11 for global hotkey capture.",
                "Log out and pick a Cinnamon (or *Xorg) session at the login screen.",
            ]
        return ["X11 session: no extra permissions required for global hotkeys."]

    def get_microphone_permission_help(self) -> list[str]:
        return [
            "Microphone: ensure PulseAudio/PipeWire is running (pactl info).",
            "If recording fails, check the user is in the 'audio' group: groups | grep audio",
        ]

    def has_global_key_access(self) -> bool:
        return not _is_wayland()
