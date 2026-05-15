from __future__ import annotations

import logging
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

import rumps

from talk_to_vibe.audio.recorder import AudioRecorder
from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.platforms.detect import get_platform
from talk_to_vibe import __version__
from talk_to_vibe.config.loader import load_config, save_config
from talk_to_vibe.runtime_paths import APP_BUNDLE_NAME, APP_NAME, INSTALLED_CONFIGURE_HELPER_PATH, configure_file_logging

TITLE_IDLE = "🎤"
TITLE_RECORDING = "🔴"
TITLE_TRANSCRIBING = "⏳"
STALE_KEY_STATE_SECONDS = 2.0
STALE_CHORD_ARM_SECONDS = 2.0


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


class TalkToVibeMenuBar(rumps.App):
    def __init__(
        self,
        stt: BaseSTTProvider,
        ptt_key_name: str = "alt_r",
        auto_enter: bool = False,
        prompt_file: str = "",
        mic_preferences: list[str] | None = None,
    ):
        super().__init__(TITLE_IDLE, quit_button=None)
        self.logger = configure_file_logging("talktovibe.menubar")
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
        self._pending_title: str | None = None
        self._ui_actions: list[tuple[str, tuple[str, str]]] = []
        self._ui_lock = threading.Lock()
        self._title_timer = rumps.Timer(self._apply_pending_title, 0.1)
        self._title_timer.start()

        self._auto_enter_item = rumps.MenuItem(
            f"Auto-Enter: {'ON ✅' if auto_enter else 'OFF'}",
            callback=self._toggle_auto_enter,
        )
        self.menu = [
            rumps.MenuItem("Provider Info", callback=self._show_provider_info),
            self._auto_enter_item,
            None,
            rumps.MenuItem("Reconfigure...", callback=self._reconfigure),
            None,
            rumps.MenuItem("About", callback=self._show_about),
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    def _notify(self, subtitle: str, message: str):
        if threading.current_thread() is threading.main_thread():
            self._run_ui_action("notify", subtitle, message)
            return
        self._queue_ui_action("notify", subtitle, message)

    def _queue_ui_action(self, action: str, title: str, message: str):
        with self._ui_lock:
            self._ui_actions.append((action, (title, message)))

    def _run_ui_action(self, action: str, title: str, message: str):
        try:
            if action == "notify":
                rumps.notification(APP_NAME, title, message)
            else:
                rumps.alert(title, message)
        except Exception:
            if action == "notify":
                self.logger.exception("Failed to send notification: %s - %s", title, message)
            else:
                self.logger.exception("Failed to show alert: %s - %s", title, message)

    def _alert(self, title: str, message: str):
        if threading.current_thread() is threading.main_thread():
            self._run_ui_action("alert", title, message)
            return
        self._queue_ui_action("alert", title, message)

    def _handle_recorder_error(self, message: str):
        self.logger.error(message)
        self._notify("Microphone", message[:150])
        self._alert("Microphone Access", message)

    def _ensure_global_key_access(self) -> bool:
        status = self.platform.get_global_key_access_status()
        if all(status.values()):
            return True

        self.logger.warning("Global key access is not granted for ptt_key=%s status=%s", self.ptt_key_name, status)
        self.platform.request_global_key_access()
        permission_lines = "\n".join(self.platform.get_global_key_permission_help())
        self._notify(
            "Permissions Required",
            f"TalkToVibe may need Input Monitoring or Accessibility for {self.ptt_key_name}. Check System Settings if the hotkey does not work.",
        )
        self.logger.warning("Global key access help for ptt_key=%s:\n%s", self.ptt_key_name, permission_lines)
        return False

    def _set_title(self, title: str):
        self._pending_title = title

    def _apply_pending_title(self, _):
        if self._pending_title is not None:
            self.title = self._pending_title
            self._pending_title = None
        self._flush_ui_actions()

    def _flush_ui_actions(self):
        with self._ui_lock:
            actions = self._ui_actions
            self._ui_actions = []
        for action, (title, message) in actions:
            self._run_ui_action(action, title, message)

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

    def _start_listener(self):
        try:
            from pynput import keyboard

            has_access = self._ensure_global_key_access()
            listener_kwargs = self.platform.build_listener_kwargs(self.logger, self.debug_key_events)

            listener = keyboard.Listener(
                on_press=self.on_key_press,
                on_release=self.on_key_release,
                **listener_kwargs,
            )
            listener.daemon = True
            listener.start()
            chord_display = self.platform.get_chord_display_name(self.ptt_key_name)
            self.logger.info("Started global keyboard listener for ptt_key=%s (%s)", self.ptt_key_name, chord_display)
            if not has_access:
                self.logger.warning(
                    "Listener started despite missing preflight access for ptt_key=%s; waiting to see if macOS actually delivers events",
                    self.ptt_key_name,
                )
            if hasattr(listener, "_thread") and listener._thread is not None:
                thread = listener._thread

                def log_listener_failure():
                    thread.join()
                    if not getattr(listener, "running", False):
                        self.logger.warning("Global keyboard listener thread exited for ptt_key=%s", self.ptt_key_name)

                threading.Thread(target=log_listener_failure, daemon=True).start()
        except Exception as exc:
            self.logger.exception("Failed to start global keyboard listener for ptt_key=%s", self.ptt_key_name)
            self._alert(
                "Global Key Listener Error",
                f"TalkToVibe failed to start the global keyboard listener for {self.ptt_key_name}.\n\n{exc}",
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
            self._set_title(TITLE_RECORDING)
            self.logger.info("Recording started for ptt_key=%s", self.ptt_key_name)
            return
        self.is_recording = False
        self._set_title(TITLE_IDLE)
        self._reset_chord_state("recording start failed")
        self.logger.warning("Recording did not start for ptt_key=%s", self.ptt_key_name)

    def _stop_recording(self):
        self.is_recording = False
        self.logger.info("Recording stopped for ptt_key=%s", self.ptt_key_name)
        audio_data, duration = self.recorder.stop()

        if audio_data is None:
            self._set_title(TITLE_IDLE)
            return

        self.processing = True
        self._set_title(TITLE_TRANSCRIBING)
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
            self._notify("Error", str(e)[:100])
        finally:
            self.processing = False
            self._set_title(TITLE_IDLE)
            if not self.is_recording:
                self._reset_chord_state("processing finished", level=logging.INFO)

    def _toggle_auto_enter(self, _):
        self.auto_enter = not self.auto_enter
        self._auto_enter_item.title = f"Auto-Enter: {'ON ✅' if self.auto_enter else 'OFF'}"
        config = load_config()
        config.auto_enter = self.auto_enter
        save_config(config)

    def _show_provider_info(self, _):
        chord_display = self.platform.get_chord_display_name(self.ptt_key_name)
        self._alert(
            "Provider Info",
            f"Provider: {self.stt.provider_name}\n"
            f"Model: {self.stt.model}\n"
            f"PTT Key: {chord_display}\n"
            f"Auto-Enter: {'ON' if self.auto_enter else 'OFF'}",
        )

    def _reconfigure(self, _):
        helper_path = INSTALLED_CONFIGURE_HELPER_PATH
        if helper_path.exists():
            command = ["open", "-a", "Terminal", str(helper_path), "--setup"]
            self.logger.info("Launching installed reconfigure helper: %s", command)
            subprocess.Popen(command)
            self._alert("Reconfigure", f"Follow the prompts in the Terminal window.\nQuit and relaunch {APP_BUNDLE_NAME} when done.")
            return

        repo_run_ttv = Path(__file__).resolve().parents[1] / "run_ttv.sh"
        if repo_run_ttv.exists():
            command = ["open", "-a", "Terminal", repo_run_ttv, "--setup"]
            self.logger.info("Launching repo reconfigure helper: %s", command)
            subprocess.Popen(command)
            self._alert("Reconfigure", f"Follow the prompts in the Terminal window.\nQuit and relaunch {APP_BUNDLE_NAME} when done.")
            return

        self.logger.warning("No configure helper found at %s or in repo checkout", helper_path)
        self._alert(
            "Reconfigure",
            "No setup helper was found. Re-run ./setup_macos.sh from the repo to repair the installation.",
        )

    def _show_about(self, _):
        self._alert("About TalkToVibe", f"TalkToVibe v{__version__}\nPush-to-talk speech-to-text")

    def _cleanup(self):
        if self.is_recording:
            self.is_recording = False
            self.recorder.stop()
        self._reset_chord_state("cleanup", level=logging.INFO)

    def _quit(self, _):
        self._cleanup()
        rumps.quit_application()

    def run(self):
        self.logger.info("Launching menu bar app with ptt_key=%s", self.ptt_key_name)
        self._start_listener()
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_sigint)
        try:
            super().run()
        finally:
            signal.signal(signal.SIGINT, original_handler)
            self.logger.info("Menu bar app exiting")

    def _handle_sigint(self, signum, frame):
        self._cleanup()
        rumps.quit_application()
