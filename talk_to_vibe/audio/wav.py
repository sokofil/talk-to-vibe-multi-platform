import os
import tempfile
import wave

import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


def audio_to_wav_file(audio_data: np.ndarray, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())
    return tmp.name


def audio_to_wav_bytes(audio_data: np.ndarray, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> bytes:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())
    return buf.getvalue()
