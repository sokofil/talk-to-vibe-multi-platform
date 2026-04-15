import base64

import numpy as np
import httpx

from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.audio.wav import audio_to_wav_bytes
from talk_to_vibe.errors import ProviderError, ProviderResponseError
from talk_to_vibe.providers.prompts import load_prompt, load_custom_prompt


class OpenRouterMultimodalProvider(BaseSTTProvider):
    provider_name = "OpenRouter"

    def __init__(self, api_key: str, model: str, base_url: str, prompt_file: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.prompt_file = prompt_file

    def transcribe(self, audio_data: np.ndarray) -> str:
        wav_bytes = audio_to_wav_bytes(audio_data)
        b64_audio = base64.b64encode(wav_bytes).decode("utf-8")

        payload = self._build_payload(b64_audio)
        response = self._send_request(payload)
        return self._parse_response(response)

    def _get_prompt(self) -> str:
        if self.prompt_file:
            return load_custom_prompt(self.prompt_file)
        return load_prompt("transcription")

    def _build_payload(self, b64_audio: str) -> dict:
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._get_prompt()},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": b64_audio,
                                "format": "wav",
                            },
                        },
                    ],
                }
            ],
            "temperature": 0,
        }

    def _send_request(self, payload: dict) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(self.base_url, json=payload, headers=headers, timeout=60.0)
        except httpx.RequestError as exc:
            raise ProviderError(f"OpenRouter request failed: {exc}") from exc
        return resp

    def _parse_response(self, response: httpx.Response) -> str:
        if response.status_code >= 400:
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                raise ProviderResponseError(
                    f"OpenRouter returned HTML (status {response.status_code}). "
                    "This usually means the endpoint URL is wrong or the API key is invalid."
                )
            try:
                error_body = response.json()
                error_msg = error_body.get("error", {}).get("message", response.text[:200])
            except Exception:
                error_msg = response.text[:200]
            raise ProviderResponseError(
                f"OpenRouter error (status {response.status_code}): {error_msg}"
            )

        try:
            body = response.json()
        except Exception as exc:
            raise ProviderResponseError(
                f"OpenRouter returned non-JSON response: {response.text[:200]}"
            ) from exc

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderResponseError(
                f"Unexpected OpenRouter response structure: {str(body)[:200]}"
            ) from exc

        result = text.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        return result
