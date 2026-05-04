import sys
import types

import numpy as np

from talk_to_vibe.providers.local_whisper import LocalWhisperProvider


class TestLocalWhisperProvider:
    def test_transcribe_joins_segments_with_spaces(self, monkeypatch):
        class FakeWhisperModel:
            def __init__(self, model_size, **kwargs):
                self.model_size = model_size
                self.kwargs = kwargs

            def transcribe(self, samples, language, beam_size, vad_filter):
                segments = [
                    types.SimpleNamespace(text="Hello"),
                    types.SimpleNamespace(text="world"),
                    types.SimpleNamespace(text=" from Whisper "),
                    types.SimpleNamespace(text=""),
                ]
                return segments, object()

        monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel))

        provider = LocalWhisperProvider(model_size="small", device="cpu", compute_type="int8")
        audio = np.zeros((16000, 1), dtype=np.int16)

        assert provider.transcribe(audio) == "Hello world from Whisper"
