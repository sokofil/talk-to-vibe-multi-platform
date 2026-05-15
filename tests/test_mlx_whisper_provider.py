from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")


@darwin_only
class TestMLXWhisperProvider:
    def _make_provider(self, **kwargs):
        with patch("talk_to_vibe.providers.mlx_whisper.load_prompt", return_value=""), \
             patch("mlx_whisper.transcribe"):
            from talk_to_vibe.providers.mlx_whisper import MLXWhisperProvider
            return MLXWhisperProvider(**kwargs)

    def test_provider_name(self):
        p = self._make_provider()
        assert "MLX" in p.provider_name

    def test_model_stored(self):
        p = self._make_provider(model="mlx-community/whisper-small-mlx-q4")
        assert p.model == "mlx-community/whisper-small-mlx-q4"

    def test_transcribe_returns_text(self):
        p = self._make_provider()
        audio = np.zeros(16000, dtype=np.float32)
        with patch("mlx_whisper.transcribe", return_value={"text": " hello world"}):
            result = p.transcribe(audio)
        assert result == "hello world"

    def test_transcribe_empty_audio_returns_empty(self):
        p = self._make_provider()
        result = p.transcribe(None)
        assert result == ""

    def test_transcribe_stream_yields_text(self):
        p = self._make_provider(post_process=False)
        audio = np.zeros(16000, dtype=np.float32)
        with patch("mlx_whisper.transcribe", return_value={"text": " hello"}):
            chunks = list(p.transcribe_stream(audio))
        assert chunks == ["hello"]

    def test_transcribe_stream_empty_result(self):
        p = self._make_provider()
        audio = np.zeros(16000, dtype=np.float32)
        with patch("mlx_whisper.transcribe", return_value={"text": ""}):
            chunks = list(p.transcribe_stream(audio))
        assert chunks == []

    def test_int16_audio_converted(self):
        p = self._make_provider(post_process=False)
        audio = np.zeros(16000, dtype=np.int16)
        calls = []
        def fake_transcribe(arr, **kwargs):
            calls.append(arr)
            return {"text": "ok"}
        with patch("mlx_whisper.transcribe", side_effect=fake_transcribe):
            list(p.transcribe_stream(audio))
        assert calls[0].dtype == np.float32

    def test_stereo_audio_converted_to_mono(self):
        p = self._make_provider(post_process=False)
        audio = np.zeros((16000, 2), dtype=np.float32)
        calls = []
        def fake_transcribe(arr, **kwargs):
            calls.append(arr)
            return {"text": "ok"}
        with patch("mlx_whisper.transcribe", side_effect=fake_transcribe):
            list(p.transcribe_stream(audio))
        assert calls[0].ndim == 1

    def test_language_passed_to_transcribe(self):
        p = self._make_provider(language="en", post_process=False)
        audio = np.zeros(16000, dtype=np.float32)
        calls = []
        def fake_transcribe(arr, **kwargs):
            calls.append(kwargs)
            return {"text": "ok"}
        with patch("mlx_whisper.transcribe", side_effect=fake_transcribe):
            list(p.transcribe_stream(audio))
        assert calls[0].get("language") == "en"

    def test_initial_prompt_passed_when_set(self):
        with patch("talk_to_vibe.providers.mlx_whisper.load_prompt", return_value="code hint"), \
             patch("mlx_whisper.transcribe"):
            from talk_to_vibe.providers.mlx_whisper import MLXWhisperProvider
            p = MLXWhisperProvider(post_process=False)
        audio = np.zeros(16000, dtype=np.float32)
        calls = []
        def fake_transcribe(arr, **kwargs):
            calls.append(kwargs)
            return {"text": "ok"}
        with patch("mlx_whisper.transcribe", side_effect=fake_transcribe):
            list(p.transcribe_stream(audio))
        assert calls[0].get("initial_prompt") == "code hint"
