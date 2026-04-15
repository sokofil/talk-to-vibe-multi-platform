import os

import numpy as np

from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.audio.wav import audio_to_wav_file


class GroqWhisperProvider(BaseSTTProvider):
    provider_name = "Groq"

    def __init__(self, api_key: str, model: str):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.model = model

    def transcribe(self, audio_data: np.ndarray) -> str:
        wav_path = audio_to_wav_file(audio_data)
        try:
            with open(wav_path, "rb") as f:
                result = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=f,
                )
            return result.text.strip()
        finally:
            os.unlink(wav_path)
