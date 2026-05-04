import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from talk_to_vibe.audio.wav import SAMPLE_RATE, CHANNELS, DTYPE

VIRTUAL_KEYWORDS = ["blackhole", "soundflower", "loopback", "virtual", "aggregate"]


def find_real_microphone():
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            name_lower = d["name"].lower()
            if not any(vk in name_lower for vk in VIRTUAL_KEYWORDS):
                return i, d["name"]
    return None, "system default"


class AudioRecorder:
    def __init__(self, error_callback: Callable[[str], None] | None = None):
        self.recording = False
        self.audio_frames: list[np.ndarray] = []
        self.stream = None
        self.start_time = 0.0
        self.error_callback = error_callback
        self.refresh_input_device()

    def refresh_input_device(self) -> None:
        self.device_id, self.device_name = find_real_microphone()

    def start(self) -> bool:
        self.audio_frames = []
        self.recording = True
        self.start_time = time.time()
        try:
            self.refresh_input_device()
            self._open_stream()
        except sd.PortAudioError as e:
            try:
                self._reset_audio_backend()
                self.refresh_input_device()
                self._open_stream()
            except sd.PortAudioError as retry_error:
                self.recording = False
                self._close_stream()
                message = (
                    f"Microphone error: {retry_error}. "
                    "Check System Settings -> Privacy & Security -> Microphone for TalkToVibe.app."
                )
                if self.error_callback is not None:
                    self.error_callback(message)
                else:
                    print(f"\n  ❌ {message}")
                return False
        return True

    def stop(self) -> tuple[np.ndarray | None, float]:
        self.recording = False
        duration = time.time() - self.start_time
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if duration < 0.3:
            return None, 0.0
        audio_data = np.concatenate(self.audio_frames) if self.audio_frames else None
        return audio_data, duration

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            self.audio_frames.append(indata.copy())

    def _open_stream(self) -> None:
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._audio_callback,
            blocksize=1024,
            device=self.device_id,
        )
        self.stream.start()

    def _reset_audio_backend(self) -> None:
        self._close_stream()
        sd._terminate()
        sd._initialize()

    def _close_stream(self) -> None:
        if self.stream is None:
            return
        try:
            self.stream.close()
        finally:
            self.stream = None
