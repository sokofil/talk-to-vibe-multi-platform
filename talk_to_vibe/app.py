import threading
import time

from talk_to_vibe.audio.recorder import AudioRecorder
from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.platforms.detect import get_platform
from talk_to_vibe import __version__

STALE_KEY_STATE_SECONDS = 2.0
STALE_CHORD_ARM_SECONDS = 2.0

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
        self._chord_armed = False
        self._last_key_event_at = 0.0
        self._last_chord_arm_at = 0.0

    def _reset_chord_state(self):
        self.held_keys.clear()
        self._chord_armed = False
        self._last_chord_arm_at = 0.0

    def _recover_stale_chord_state(self, now: float, key: object):
        if self.processing or not self.held_keys:
            return

        idle_for = now - self._last_key_event_at if self._last_key_event_at else 0.0
        armed_for = now - self._last_chord_arm_at if self._last_chord_arm_at else 0.0

        if idle_for >= STALE_KEY_STATE_SECONDS:
            self._reset_chord_state()
            return

        if self._chord_armed and self.held_keys == self.ptt_chord and key in self.ptt_chord and armed_for >= STALE_CHORD_ARM_SECONDS:
            self._reset_chord_state()

    def on_key_press(self, key):
        now = time.monotonic()
        normalized_key = self.platform.normalize_listener_key(key)
        self._recover_stale_chord_state(now, normalized_key)
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
            return
        self.is_recording = False
        self._reset_chord_state()

    def _stop_recording(self):
        self.is_recording = False
        audio_data, duration = self.recorder.stop()

        if audio_data is None:
            return

        self.processing = True
        threading.Thread(target=self._process, args=(audio_data, duration), daemon=True).start()

    def on_key_release(self, key):
        now = time.monotonic()
        normalized_key = self.platform.normalize_listener_key(key)
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
            if not self.is_recording:
                self._reset_chord_state()

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
        print(f"  Press chord once to start recording, press again to transcribe.")
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
