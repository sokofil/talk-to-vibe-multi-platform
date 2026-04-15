import time

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
    def __init__(self):
        self.recording = False
        self.audio_frames: list[np.ndarray] = []
        self.stream = None
        self.start_time = 0.0
        self.device_id, self.device_name = find_real_microphone()

    def start(self) -> bool:
        self.audio_frames = []
        self.recording = True
        self.start_time = time.time()
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._audio_callback,
                blocksize=1024,
                device=self.device_id,
            )
            self.stream.start()
        except sd.PortAudioError as e:
            self.recording = False
            print(f"\n  ❌ Microphone error: {e}")
            print("     Check System Settings → Privacy → Microphone")
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
