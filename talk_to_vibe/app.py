import threading
import time

from talk_to_vibe.audio.recorder import AudioRecorder
from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.platforms.detect import get_platform
from talk_to_vibe import __version__

DEBOUNCE_SECONDS = 0.05


class TalkToVibe:
    def __init__(self, stt: BaseSTTProvider, ptt_key_name: str = "alt_r", auto_enter: bool = False):
        self.platform = get_platform()
        self.recorder = AudioRecorder()
        self.stt = stt
        self.ptt_key_name = ptt_key_name
        self.auto_enter = auto_enter
        self.is_recording = False
        self.processing = False

        self.ptt_chord = self.platform.parse_ptt_chord(ptt_key_name)
        self.held_keys: set = set()
        self._debounce_timer: threading.Timer | None = None

    def on_key_press(self, key):
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
        if not self.recorder.start():
            self.is_recording = False

    def on_key_release(self, key):
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
                return

            self.processing = True
            threading.Thread(target=self._process, args=(audio_data, duration), daemon=True).start()

    def _process(self, audio_data, duration):
        try:
            start = time.time()
            text = self.stt.transcribe(audio_data)
            elapsed = time.time() - start

            if text:
                print(f'  📝 "{text}" ({elapsed:.1f}s)')
                self.platform.paste_text(text, auto_enter=self.auto_enter)
                self.platform.play_success_sound()
            else:
                print("  (empty result)")
        except Exception as e:
            print(f"\n  ❌ Error: {e}")
        finally:
            self.processing = False

    def run(self):
        from pynput import keyboard

        ptt_display = self.platform.get_chord_display_name(self.ptt_key_name)
        print("━" * 50)
        print(f"🎤 Talk to Vibe v{__version__}")
        print("━" * 50)
        print(f"  PTT Key:    {ptt_display}")
        print(f"  Mic:        {self.recorder.device_name}")
        print(f"  Provider:   {self.stt.provider_name}")
        print(f"  Model:      {self.stt.model}")
        print(f"  Auto-Enter: {'ON' if self.auto_enter else 'OFF'}")
        print(f"  Hold key to record, release to transcribe.")
        print(f"  Result is auto-pasted to current app.")
        print(f"  Press Ctrl+C to quit.")
        print("━" * 50)
        print()

        for line in self.platform.get_permission_help():
            print(f"⚠️  Make sure to allow: {line}")
        print()

        with keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release,
        ) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\n\n👋 Bye!")
