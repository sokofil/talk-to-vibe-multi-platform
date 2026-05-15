from __future__ import annotations

import numpy as np

from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.providers.prompts import load_prompt, load_custom_prompt


def _load_hints(hints_file: str) -> str:
    try:
        if hints_file:
            return load_custom_prompt(hints_file)
        return load_prompt("whisper_hints")
    except FileNotFoundError:
        return ""


class MLXWhisperProvider(BaseSTTProvider):
    provider_name = "MLX Whisper (Apple Silicon)"

    def __init__(
        self,
        model: str = "mlx-community/whisper-large-v3-turbo",
        language: str = "",
        hints_file: str = "",
        post_process: bool = True,
    ):
        import mlx_whisper  # noqa: F401 — validate import at init time

        self.model = model
        self.language = language or None
        self.post_process = post_process
        self.initial_prompt = _load_hints(hints_file)

    def transcribe(self, audio_data: np.ndarray) -> str:
        return " ".join(self.transcribe_stream(audio_data)).strip()

    def transcribe_stream(self, audio_data: np.ndarray):
        import mlx_whisper

        if audio_data is None or len(audio_data) == 0:
            return

        if audio_data.dtype == np.int16:
            samples = audio_data.astype(np.float32) / 32768.0
        elif audio_data.dtype == np.float32:
            samples = audio_data
        else:
            samples = audio_data.astype(np.float32)

        if samples.ndim > 1:
            samples = samples.mean(axis=1).astype(np.float32)

        decode_options: dict = {"task": "transcribe"}
        if self.language:
            decode_options["language"] = self.language

        result = mlx_whisper.transcribe(
            samples,
            path_or_hf_repo=self.model,
            verbose=False,
            initial_prompt=self.initial_prompt or None,
            **decode_options,
        )

        text = result.get("text", "").strip()
        if not text:
            return

        if self.post_process:
            from talk_to_vibe.providers.post_process import clean_transcript
            text = clean_transcript(text)

        if text:
            yield text
