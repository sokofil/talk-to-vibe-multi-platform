import os
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
from talk_to_vibe.providers.factory import create_provider

DEBOUNCE_SECONDS = 0.05

TITLE_IDLE = "🎤"
TITLE_RECORDING = "🔴"
TITLE_TRANSCRIBING = "⏳"


class TalkToVibeMenuBar(rumps.App):
    def __init__(self, stt: BaseSTTProvider, ptt_key_name: str = "alt_r", auto_enter: bool = False, prompt_file: str = ""):
        super().__init__(TITLE_IDLE, quit_button=None)
        self.stt = stt
        self.ptt_key_name = ptt_key_name
        self.auto_enter = auto_enter
        self.prompt_file = prompt_file
        self.platform = get_platform()
        self.recorder = AudioRecorder()
        self.is_recording = False
        self.processing = False
        self.ptt_chord = self.platform.parse_ptt_chord(ptt_key_name)
        self.held_keys: set = set()
        self._debounce_timer: threading.Timer | None = None
        self._paste_in_progress = False
        self._pending_title: str | None = None
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

    def _set_title(self, title: str):
        self._pending_title = title

    def _apply_pending_title(self, _):
        if self._pending_title is not None:
            self.title = self._pending_title
            self._pending_title = None

    def _start_listener(self):
        from pynput import keyboard

        listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release,
        )
        listener.daemon = True
        listener.start()

    def on_key_press(self, key):
        if self._paste_in_progress:
            return

        self.held_keys.add(key)

        if self.is_recording or self.processing:
            return

        if self.held_keys == self.ptt_chord:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(DEBOUNCE_SECONDS, self._start_recording)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()
        else:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None

    def _start_recording(self):
        self._debounce_timer = None
        if self.held_keys != self.ptt_chord:
            return
        self.is_recording = True
        self._set_title(TITLE_RECORDING)
        if not self.recorder.start():
            self.is_recording = False
            self._set_title(TITLE_IDLE)

    def on_key_release(self, key):
        if self._paste_in_progress:
            return

        self.held_keys.discard(key)

        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None

        if not self.is_recording:
            return

        if key in self.ptt_chord:
            self.is_recording = False
            audio_data, duration = self.recorder.stop()

            if audio_data is None:
                self._set_title(TITLE_IDLE)
                return

            self.processing = True
            self._set_title(TITLE_TRANSCRIBING)
            threading.Thread(target=self._process, args=(audio_data, duration), daemon=True).start()

    def _process(self, audio_data, duration):
        try:
            start = time.time()
            text = self.stt.transcribe(audio_data)
            elapsed = time.time() - start

            if text:
                self._paste_in_progress = True
                try:
                    self.platform.paste_text(text, auto_enter=self.auto_enter)
                finally:
                    self._paste_in_progress = False
                self.platform.play_success_sound()
                rumps.notification(
                    "Talk to Vibe",
                    f"Transcribed ({elapsed:.1f}s)",
                    text[:100],
                )
            else:
                rumps.notification("Talk to Vibe", "Empty", "No speech detected")
        except Exception as e:
            rumps.notification("Talk to Vibe", "Error", str(e)[:100])
        finally:
            self.processing = False
            self._set_title(TITLE_IDLE)

    def _toggle_auto_enter(self, _):
        self.auto_enter = not self.auto_enter
        self._auto_enter_item.title = f"Auto-Enter: {'ON ✅' if self.auto_enter else 'OFF'}"
        config = load_config()
        config.auto_enter = self.auto_enter
        save_config(config)

    def _show_provider_info(self, _):
        chord_display = self.platform.get_chord_display_name(self.ptt_key_name)
        rumps.alert(
            "Provider Info",
            f"Provider: {self.stt.provider_name}\n"
            f"Model: {self.stt.model}\n"
            f"PTT Key: {chord_display}\n"
            f"Auto-Enter: {'ON' if self.auto_enter else 'OFF'}",
        )

    def _reconfigure(self, _):
        run_ttv = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'run_ttv.sh'))
        subprocess.Popen(["open", "-a", "Terminal", run_ttv, "--setup"])
        rumps.alert("Reconfigure", "Follow the prompts in the Terminal window.\nQuit and relaunch Talk to Vibe when done.")

    def _show_about(self, _):
        rumps.alert("About Talk to Vibe", f"Talk to Vibe v{__version__}\nPush-to-talk speech-to-text")

    def _cleanup(self):
        if self.is_recording:
            self.is_recording = False
            self.recorder.stop()
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        self.held_keys.clear()

    def _quit(self, _):
        self._cleanup()
        rumps.quit_application()

    def run(self):
        self._start_listener()
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_sigint)
        try:
            super().run()
        finally:
            signal.signal(signal.SIGINT, original_handler)

    def _handle_sigint(self, signum, frame):
        self._cleanup()
        rumps.quit_application()
