import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from talk_to_vibe.audio.recorder import AudioRecorder
from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.platforms.detect import get_platform
from talk_to_vibe import __version__
from talk_to_vibe.config.loader import load_config, save_config
from talk_to_vibe.runtime_paths import APP_NAME, configure_file_logging

ICON_IDLE = "idle"
ICON_RECORDING = "recording"
ICON_TRANSCRIBING = "transcribing"
STALE_KEY_STATE_SECONDS = 2.0
STALE_CHORD_ARM_SECONDS = 2.0

_TERMINAL_CANDIDATES = (
    ("gnome-terminal", ["--", "bash", "-lc"]),
    ("cinnamon-terminal", ["-e", "bash -lc"]),
    ("xfce4-terminal", ["-x", "bash", "-lc"]),
    ("konsole", ["-e", "bash", "-lc"]),
    ("xterm", ["-e", "bash", "-lc"]),
    ("x-terminal-emulator", ["-e", "bash", "-lc"]),
)


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_state_icons():
    from PIL import Image, ImageDraw

    size = 64
    images: dict[str, Image.Image] = {}

    idle = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(idle)
    d.rounded_rectangle((22, 8, 42, 38), radius=10, fill=(60, 60, 60, 255))
    d.arc((14, 22, 50, 52), start=0, end=180, fill=(60, 60, 60, 255), width=4)
    d.rectangle((30, 46, 34, 56), fill=(60, 60, 60, 255))
    d.rectangle((20, 54, 44, 58), fill=(60, 60, 60, 255))
    images[ICON_IDLE] = idle

    recording = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(recording)
    d.ellipse((10, 10, 54, 54), fill=(220, 30, 30, 255))
    images[ICON_RECORDING] = recording

    transcribing = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(transcribing)
    d.polygon(
        [(18, 12), (46, 12), (32, 32), (46, 52), (18, 52), (32, 32)],
        fill=(200, 140, 0, 255),
    )
    images[ICON_TRANSCRIBING] = transcribing

    return images


class TalkToVibeTray:
    def __init__(
        self,
        stt: BaseSTTProvider,
        ptt_key_name: str = "ctrl+9",
        auto_enter: bool = False,
        prompt_file: str = "",
        mic_preferences: list[str] | None = None,
    ):
        self.logger = configure_file_logging("talktovibe.tray")
        self.stt = stt
        self.ptt_key_name = ptt_key_name
        self.auto_enter = auto_enter
        self.prompt_file = prompt_file
        self.platform = get_platform()
        self.recorder = AudioRecorder(
            error_callback=self._handle_recorder_error,
            mic_preferences=mic_preferences,
        )
        self.is_recording = False
        self.processing = False
        self.debug_key_events = _env_flag_enabled("TALKTOVIBE_DEBUG_KEYS")
        self.ptt_chord = self.platform.parse_ptt_chord(ptt_key_name)
        self.held_keys: set = set()
        self._chord_armed = False
        self._last_key_event_at = 0.0
        self._last_chord_arm_at = 0.0
        self._paste_in_progress = False
        self._icons = build_state_icons()
        self._current_state = ICON_IDLE
        self._tray = None
        self._chord_grabber = None

    def _build_menu(self):
        import pystray

        def auto_enter_label(_item):
            return f"Auto-Enter: {'ON' if self.auto_enter else 'OFF'}"

        return pystray.Menu(
            pystray.MenuItem("Provider Info", self._show_provider_info),
            pystray.MenuItem(auto_enter_label, self._toggle_auto_enter),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Reconfigure...", self._reconfigure),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("About", self._show_about),
            pystray.MenuItem("Quit", self._quit),
        )

    def _build_tray(self):
        import pystray

        return pystray.Icon(
            APP_NAME,
            icon=self._icons[ICON_IDLE],
            title=APP_NAME,
            menu=self._build_menu(),
        )

    def _set_state(self, state: str):
        self._current_state = state
        if self._tray is None:
            return
        try:
            self._tray.icon = self._icons[state]
        except Exception:
            self.logger.exception("Failed to update tray icon to state=%s", state)

    def _notify(self, summary: str, message: str):
        if shutil.which("notify-send") is None:
            self.logger.info("notify-send missing, dropping notification: %s — %s", summary, message)
            return
        try:
            subprocess.Popen(
                ["notify-send", "--app-name", APP_NAME, f"{APP_NAME}: {summary}", message[:300]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self.logger.exception("Failed to send notification: %s — %s", summary, message)

    def _handle_recorder_error(self, message: str):
        self.logger.error(message)
        self._notify("Microphone", message[:150])

    def _ensure_global_key_access(self) -> bool:
        if self.platform.has_global_key_access():
            return True
        permission_lines = "\n".join(self.platform.get_global_key_permission_help())
        self.logger.warning(
            "Global key access unavailable for ptt_key=%s\n%s",
            self.ptt_key_name,
            permission_lines,
        )
        self._notify(
            "Global hotkey unavailable",
            "Wayland session detected. Switch to an X11 (Cinnamon) session to enable the push-to-talk hotkey.",
        )
        return False

    def _reset_chord_state(self, reason: str, *, level: int = logging.WARNING):
        if self.held_keys or self._chord_armed:
            self.logger.log(
                level,
                "Resetting chord state for ptt_key=%s reason=%s held=%s armed=%s recording=%s processing=%s",
                self.ptt_key_name,
                reason,
                sorted(repr(k) for k in self.held_keys),
                self._chord_armed,
                self.is_recording,
                self.processing,
            )
        self.held_keys.clear()
        self._chord_armed = False
        self._last_chord_arm_at = 0.0

    def _recover_stale_chord_state(self, now: float, key: object):
        if self.processing or self._paste_in_progress or not self.held_keys:
            return

        idle_for = now - self._last_key_event_at if self._last_key_event_at else 0.0
        armed_for = now - self._last_chord_arm_at if self._last_chord_arm_at else 0.0

        if idle_for >= STALE_KEY_STATE_SECONDS:
            self._reset_chord_state(f"no key events for {idle_for:.2f}s before {key!r}")
            return

        if self._chord_armed and self.held_keys == self.ptt_chord and key in self.ptt_chord and armed_for >= STALE_CHORD_ARM_SECONDS:
            self._reset_chord_state(f"chord remained armed for {armed_for:.2f}s before repeated {key!r}")

    def _log_key_event(self, action: str, raw_key: object, normalized_key: object):
        if not self.debug_key_events:
            return
        self.logger.info(
            "Key %s raw=%s normalized=%s held_before=%s target=%s",
            action,
            self.platform.describe_listener_key(raw_key),
            repr(normalized_key),
            sorted(repr(k) for k in self.held_keys),
            sorted(repr(k) for k in self.ptt_chord),
        )

    def _start_chord_grabber(self):
        try:
            from talk_to_vibe.platforms.linux_xgrab import XChordGrabber
        except Exception:
            self.logger.exception("Failed to import XChordGrabber")
            return
        self._chord_grabber = XChordGrabber(self.ptt_key_name, logger=self.logger)
        if not self._chord_grabber.start():
            self.logger.info(
                "Chord %r not grabbed at X server; the key may leak to focused windows.",
                self.ptt_key_name,
            )
            self._chord_grabber = None

    def _start_listener(self):
        try:
            from pynput import keyboard

            has_access = self._ensure_global_key_access()
            self._start_chord_grabber()
            listener_kwargs = self.platform.build_listener_kwargs(self.logger, self.debug_key_events)

            listener = keyboard.Listener(
                on_press=self.on_key_press,
                on_release=self.on_key_release,
                **listener_kwargs,
            )
            listener.daemon = True
            listener.start()
            chord_display = self.platform.get_chord_display_name(self.ptt_key_name)
            self.logger.info(
                "Started global keyboard listener for ptt_key=%s (%s)",
                self.ptt_key_name,
                chord_display,
            )
            if not has_access:
                self.logger.warning(
                    "Listener started despite missing global key access for ptt_key=%s",
                    self.ptt_key_name,
                )
        except Exception as exc:
            self.logger.exception("Failed to start global keyboard listener for ptt_key=%s", self.ptt_key_name)
            self._notify(
                "Global Key Listener Error",
                f"TalkToVibe failed to start the global keyboard listener for {self.ptt_key_name}: {exc}",
            )

    def on_key_press(self, key):
        if self._paste_in_progress:
            return

        now = time.monotonic()
        normalized_key = self.platform.normalize_listener_key(key)
        self._recover_stale_chord_state(now, normalized_key)
        self._log_key_event("press", key, normalized_key)
        self.held_keys.add(normalized_key)
        self._last_key_event_at = now

        if self.processing:
            return

        if self.held_keys != self.ptt_chord:
            return

        if self._chord_armed:
            return

        self._chord_armed = True
        self._last_chord_arm_at = now
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if self.recorder.start():
            self.is_recording = True
            self._set_state(ICON_RECORDING)
            self.logger.info("Recording started for ptt_key=%s", self.ptt_key_name)
            return
        self.is_recording = False
        self._set_state(ICON_IDLE)
        self._reset_chord_state("recording start failed")
        self.logger.warning("Recording did not start for ptt_key=%s", self.ptt_key_name)

    def _stop_recording(self):
        self.is_recording = False
        self.logger.info("Recording stopped for ptt_key=%s", self.ptt_key_name)
        audio_data, duration = self.recorder.stop()

        if audio_data is None:
            self._set_state(ICON_IDLE)
            return

        self.processing = True
        self._set_state(ICON_TRANSCRIBING)
        threading.Thread(target=self._process, args=(audio_data, duration), daemon=True).start()

    def on_key_release(self, key):
        if self._paste_in_progress:
            return

        now = time.monotonic()
        normalized_key = self.platform.normalize_listener_key(key)
        self._log_key_event("release", key, normalized_key)
        self.held_keys.discard(normalized_key)
        self._last_key_event_at = now

        if normalized_key in self.ptt_chord and self.held_keys != self.ptt_chord:
            self._chord_armed = False
            self._last_chord_arm_at = 0.0

    def _process(self, audio_data, duration):
        try:
            start = time.time()
            text = self.stt.transcribe(audio_data)
            elapsed = time.time() - start
            self.logger.info("Transcription completed in %.2fs", elapsed)

            if text:
                self._paste_in_progress = True
                try:
                    paste_result = self.platform.paste_text(text, auto_enter=self.auto_enter)
                finally:
                    self._paste_in_progress = False
                if paste_result.clipboard_restore_failed:
                    self._notify("Clipboard", "Dictation was inserted, but the previous clipboard could not be restored.")
                self.platform.play_success_sound()
                self.logger.info("Transcribed in %.2fs: %s", elapsed, text[:100])
            else:
                self.logger.info("Empty transcription — no speech detected")
                self._notify("Empty", "No speech detected")
        except Exception as e:
            self.logger.exception("Transcription failed")
            self._notify("Error", str(e)[:200])
        finally:
            self.processing = False
            self._set_state(ICON_IDLE)
            if not self.is_recording:
                self._reset_chord_state("processing finished", level=logging.INFO)

    def _toggle_auto_enter(self, _icon=None, _item=None):
        self.auto_enter = not self.auto_enter
        config = load_config()
        config.auto_enter = self.auto_enter
        save_config(config)
        if self._tray is not None:
            try:
                self._tray.update_menu()
            except Exception:
                self.logger.exception("Failed to refresh tray menu")
        self._notify(
            "Auto-Enter",
            f"Auto-Enter is now {'ON' if self.auto_enter else 'OFF'}",
        )

    def _show_provider_info(self, _icon=None, _item=None):
        chord_display = self.platform.get_chord_display_name(self.ptt_key_name)
        message = (
            f"Provider: {self.stt.provider_name}\n"
            f"Model: {self.stt.model}\n"
            f"PTT Key: {chord_display}\n"
            f"Auto-Enter: {'ON' if self.auto_enter else 'OFF'}"
        )
        self._notify("Provider Info", message)

    def _reconfigure(self, _icon=None, _item=None):
        repo_run_ttv = Path(__file__).resolve().parents[1] / "run_ttv.sh"
        if not repo_run_ttv.exists():
            self._notify(
                "Reconfigure",
                f"Could not locate run_ttv.sh next to the package: {repo_run_ttv}",
            )
            return
        command = self._build_terminal_command(f"{repo_run_ttv} --setup; echo; echo 'Press Enter to close'; read")
        if command is None:
            self._notify(
                "Reconfigure",
                "No supported terminal found. Run ./run_ttv.sh --setup manually.",
            )
            return
        try:
            subprocess.Popen(command)
        except Exception:
            self.logger.exception("Failed to launch terminal for reconfigure: %s", command)
            self._notify("Reconfigure", "Failed to open a terminal. Run ./run_ttv.sh --setup manually.")
            return
        self._notify(
            "Reconfigure",
            "Follow the prompts in the terminal window. Quit and relaunch TalkToVibe when done.",
        )

    def _build_terminal_command(self, shell_cmd: str) -> list[str] | None:
        env_terminal = os.environ.get("TERMINAL")
        if env_terminal and shutil.which(env_terminal):
            return [env_terminal, "-e", "bash", "-lc", shell_cmd]
        for name, args in _TERMINAL_CANDIDATES:
            if shutil.which(name) is None:
                continue
            return [name, *args, shell_cmd]
        return None

    def _show_about(self, _icon=None, _item=None):
        self._notify("About TalkToVibe", f"TalkToVibe v{__version__} — push-to-talk speech-to-text")

    def _cleanup(self):
        if self.is_recording:
            self.is_recording = False
            self.recorder.stop()
        if self._chord_grabber is not None:
            try:
                self._chord_grabber.stop()
            except Exception:
                self.logger.exception("Failed to stop chord grabber")
            self._chord_grabber = None
        self._reset_chord_state("cleanup", level=logging.INFO)

    def _quit(self, _icon=None, _item=None):
        self._cleanup()
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                self.logger.exception("Failed to stop tray icon")

    def run(self):
        self.logger.info("Launching tray app with ptt_key=%s", self.ptt_key_name)
        self._tray = self._build_tray()
        self._start_listener()
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_sigint)
        try:
            self._tray.run()
        finally:
            signal.signal(signal.SIGINT, original_handler)
            self.logger.info("Tray app exiting")

    def _handle_sigint(self, signum, frame):
        self._quit()
