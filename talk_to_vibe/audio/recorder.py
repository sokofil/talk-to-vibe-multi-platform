from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterable

import numpy as np
import sounddevice as sd

from talk_to_vibe.audio.wav import SAMPLE_RATE, CHANNELS, DTYPE

VIRTUAL_KEYWORDS = ["blackhole", "soundflower", "loopback", "virtual", "aggregate"]
PREFERRED_LINUX_KEYWORDS = ["pipewire", "pulse", "default"]


def _device_accepts_settings(device_id) -> bool:
    try:
        sd.check_input_settings(
            device=device_id,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
        )
    except Exception:
        return False
    return True


def _refresh_portaudio() -> None:
    # Force PortAudio to re-enumerate devices so hot-plugged mics (e.g. on a
    # KVM switch) show up. _terminate/_initialize are technically private but
    # are the documented workaround. Best-effort: ignore failures.
    terminate = getattr(sd, "_terminate", None)
    initialize = getattr(sd, "_initialize", None)
    if not callable(terminate) or not callable(initialize):
        return
    try:
        terminate()
        initialize()
    except Exception:
        pass


def _input_candidates() -> list[tuple[int, dict]]:
    devices = sd.query_devices()
    return [
        (i, d) for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]


def _match_first(candidates: list[tuple[int, dict]], keyword: str) -> tuple[int, str] | None:
    kw = keyword.lower().strip()
    if not kw:
        return None
    for i, d in candidates:
        if kw in d["name"].lower() and _device_accepts_settings(i):
            return i, d["name"]
    return None


def find_real_microphone(
    preferences: Iterable[str] | None = None,
    refresh: bool = True,
) -> tuple[int | None, str]:
    """Pick the best input device by name, validated against our sample rate.

    Resolution order:
      1. User preferences (case-insensitive substring match, in given order).
      2. Linux resampling layers (pipewire / pulse / default).
      3. Any non-virtual hardware device that accepts our settings.
      4. PortAudio system default.

    Identifying by name (not cached index) keeps us correct across hot-plug
    events where indices can shift.
    """
    if refresh:
        _refresh_portaudio()
    candidates = _input_candidates()

    for keyword in (preferences or []):
        match = _match_first(candidates, keyword)
        if match is not None:
            return match

    for keyword in PREFERRED_LINUX_KEYWORDS:
        match = _match_first(candidates, keyword)
        if match is not None:
            return match

    for i, d in candidates:
        name_lower = d["name"].lower()
        if any(vk in name_lower for vk in VIRTUAL_KEYWORDS):
            continue
        if _device_accepts_settings(i):
            return i, d["name"]

    if _device_accepts_settings(None):
        return None, "system default"
    return None, "system default"


class AudioRecorder:
    def __init__(
        self,
        error_callback: Callable[[str], None] | None = None,
        mic_preferences: Iterable[str] | None = None,
    ):
        self.recording = False
        self.audio_frames: list[np.ndarray] = []
        self.stream = None
        self.start_time = 0.0
        self.error_callback = error_callback
        self.mic_preferences: list[str] = [p for p in (mic_preferences or []) if p]
        self.device_id: int | None = None
        self.device_name: str = "system default"
        self.refresh_input_device(refresh_portaudio=False)

    def refresh_input_device(self, refresh_portaudio: bool = True) -> None:
        self.device_id, self.device_name = find_real_microphone(
            preferences=self.mic_preferences,
            refresh=refresh_portaudio,
        )

    def start(self) -> bool:
        # Re-resolve every time: KVM/USB hot-plug can change which devices are
        # present and PortAudio's indices between recordings.
        self.refresh_input_device(refresh_portaudio=True)
        self.audio_frames = []
        self.recording = True
        self.start_time = time.time()
        try:
            self._open_stream()
        except sd.PortAudioError:
            try:
                self._reset_audio_backend()
                self.refresh_input_device(refresh_portaudio=False)
                self._open_stream()
            except sd.PortAudioError as retry_error:
                self.recording = False
                self._close_stream()
                if sys.platform == "darwin":
                    guidance = "Check System Settings -> Privacy & Security -> Microphone for TalkToVibe.app."
                else:
                    guidance = "Check your OS sound settings; for KVM users, confirm the mic is currently routed to this machine."
                message = (
                    f"Microphone error: {retry_error} "
                    f"(device: {self.device_name!r}). "
                    f"{guidance}"
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
        terminate = getattr(sd, "_terminate", None)
        initialize = getattr(sd, "_initialize", None)
        if callable(terminate):
            terminate()
        if callable(initialize):
            initialize()

    def _close_stream(self) -> None:
        if self.stream is None:
            return
        try:
            self.stream.close()
        finally:
            self.stream = None
