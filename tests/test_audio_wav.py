import numpy as np
import pytest

from talk_to_vibe.audio.wav import audio_to_wav_file, audio_to_wav_bytes


class TestAudioToWavFile:
    def test_creates_valid_wav(self, tmp_path):
        audio = np.zeros((16000, 1), dtype=np.int16)
        wav_path = audio_to_wav_file(audio)
        try:
            assert wav_path.endswith(".wav")
            import wave
            with wave.open(wav_path, "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 16000
                assert wf.getnframes() == 16000
        finally:
            import os
            os.unlink(wav_path)

    def test_nonzero_audio_roundtrips(self, tmp_path):
        audio = np.ones((8000, 1), dtype=np.int16) * 1000
        wav_path = audio_to_wav_file(audio)
        try:
            import wave
            with wave.open(wav_path, "rb") as wf:
                assert wf.getnframes() == 8000
        finally:
            import os
            os.unlink(wav_path)


class TestAudioToWavBytes:
    def test_produces_bytes(self):
        audio = np.zeros((16000, 1), dtype=np.int16)
        data = audio_to_wav_bytes(audio)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_bytes_are_valid_wav(self):
        import io
        import wave
        audio = np.zeros((16000, 1), dtype=np.int16)
        data = audio_to_wav_bytes(audio)
        with wave.open(io.BytesIO(data), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 16000

    def test_nonzero_audio_bytes(self):
        import io
        import wave
        audio = np.ones((8000, 1), dtype=np.int16) * 500
        data = audio_to_wav_bytes(audio)
        with wave.open(io.BytesIO(data), "rb") as wf:
            assert wf.getnframes() == 8000
