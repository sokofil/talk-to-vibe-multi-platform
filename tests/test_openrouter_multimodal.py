import base64

import numpy as np
import pytest

from talk_to_vibe.providers.openrouter_multimodal import OpenRouterMultimodalProvider
from talk_to_vibe.providers.prompts import load_prompt
from talk_to_vibe.errors import ProviderError, ProviderResponseError


DEFAULT_MODEL = "google/gemini-3.1-flash-lite-preview"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


def _make_provider(**kwargs):
    defaults = {
        "api_key": "sk-or-test",
        "model": DEFAULT_MODEL,
        "base_url": DEFAULT_BASE_URL,
    }
    defaults.update(kwargs)
    return OpenRouterMultimodalProvider(**defaults)


def _make_audio_data(duration_sec: float = 1.0, sample_rate: int = 16000) -> np.ndarray:
    samples = int(duration_sec * sample_rate)
    return np.zeros((samples, 1), dtype=np.int16)


def _make_success_response(text: str) -> dict:
    return {
        "choices": [
            {
                "message": {"content": text, "role": "assistant"},
                "finish_reason": "stop",
            }
        ],
        "model": DEFAULT_MODEL,
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }


class TestBuildPayload:
    def test_payload_structure(self):
        p = _make_provider()
        b64_audio = base64.b64encode(b"fake_wav_data").decode("utf-8")
        payload = p._build_payload(b64_audio)

        assert payload["model"] == DEFAULT_MODEL
        assert payload["temperature"] == 0
        assert len(payload["messages"]) == 1

        msg = payload["messages"][0]
        assert msg["role"] == "user"
        assert len(msg["content"]) == 2

        text_part, audio_part = msg["content"]
        assert text_part["type"] == "text"
        assert text_part["text"] == load_prompt("transcription")
        assert audio_part["type"] == "input_audio"
        assert audio_part["input_audio"]["format"] == "wav"
        assert audio_part["input_audio"]["data"] == b64_audio

    def test_custom_model_in_payload(self):
        p = _make_provider(model="google/gemini-2.5-flash")
        payload = p._build_payload("fake_b64")
        assert payload["model"] == "google/gemini-2.5-flash"

    def test_custom_prompt_file_in_payload(self, tmp_path):
        custom = tmp_path / "custom.md"
        custom.write_text("My custom prompt\n")
        p = _make_provider(prompt_file=str(custom))
        payload = p._build_payload("fake_b64")
        text_part = payload["messages"][0]["content"][0]
        assert text_part["text"] == "My custom prompt"

    def test_default_prompt_when_no_file(self):
        p = _make_provider()
        payload = p._build_payload("fake_b64")
        text_part = payload["messages"][0]["content"][0]
        assert text_part["text"] == load_prompt("transcription")


class TestGetPrompt:
    def test_get_prompt_uses_bundled_by_default(self):
        p = _make_provider()
        assert p._get_prompt() == load_prompt("transcription")

    def test_get_prompt_uses_custom_file(self, tmp_path):
        custom = tmp_path / "custom.md"
        custom.write_text("Custom instructions here\n")
        p = _make_provider(prompt_file=str(custom))
        assert p._get_prompt() == "Custom instructions here"

    def test_get_prompt_missing_custom_file_raises(self):
        p = _make_provider(prompt_file="/nonexistent/prompt.md")
        with pytest.raises(FileNotFoundError):
            p._get_prompt()


class TestParseResponse:
    def test_successful_transcript(self):
        p = _make_provider()

        class FakeResp:
            status_code = 200
            headers = {"content-type": "application/json"}
            def json(self):
                return _make_success_response("Hello world")
            text = ""

        result = p._parse_response(FakeResp())
        assert result == "Hello world"

    def test_strips_whitespace(self):
        p = _make_provider()

        class FakeResp:
            status_code = 200
            headers = {"content-type": "application/json"}
            def json(self):
                return _make_success_response("  Hello world  \n")
            text = ""

        result = p._parse_response(FakeResp())
        assert result == "Hello world"

    def test_strips_surrounding_quotes(self):
        p = _make_provider()

        class FakeResp:
            status_code = 200
            headers = {"content-type": "application/json"}
            def json(self):
                return _make_success_response('"Hello world"')
            text = ""

        result = p._parse_response(FakeResp())
        assert result == "Hello world"

    def test_html_500_error(self):
        p = _make_provider()

        class FakeResp:
            status_code = 500
            headers = {"content-type": "text/html"}
            text = "<html><body>500 Internal Server Error</body></html>"

        with pytest.raises(ProviderResponseError, match="HTML"):
            p._parse_response(FakeResp())

    def test_json_error_response(self):
        p = _make_provider()

        class FakeResp:
            status_code = 401
            headers = {"content-type": "application/json"}
            def json(self):
                return {"error": {"message": "Invalid API key"}}
            text = '{"error": {"message": "Invalid API key"}}'

        with pytest.raises(ProviderResponseError, match="Invalid API key"):
            p._parse_response(FakeResp())

    def test_non_json_response(self):
        p = _make_provider()

        class FakeResp:
            status_code = 200
            headers = {"content-type": "text/plain"}
            text = "not json at all"
            def json(self):
                raise ValueError("not json")

        with pytest.raises(ProviderResponseError, match="non-JSON"):
            p._parse_response(FakeResp())

    def test_unexpected_response_structure(self):
        p = _make_provider()

        class FakeResp:
            status_code = 200
            headers = {"content-type": "application/json"}
            def json(self):
                return {"no_choices": True}
            text = '{"no_choices": true}'

        with pytest.raises(ProviderResponseError, match="Unexpected"):
            p._parse_response(FakeResp())


class TestTranscribeIntegration:
    def test_transcribe_builds_correct_request(self, monkeypatch):
        p = _make_provider(api_key="sk-or-testkey123")
        audio = _make_audio_data()

        captured_payload = {}

        class FakeResp:
            status_code = 200
            headers = {"content-type": "application/json"}
            def json(self):
                return _make_success_response("test transcript")
            text = ""

        def fake_post(url, json=None, headers=None, timeout=None):
            captured_payload["url"] = url
            captured_payload["json"] = json
            captured_payload["headers"] = headers
            captured_payload["timeout"] = timeout
            return FakeResp()

        import httpx
        monkeypatch.setattr(httpx, "post", fake_post)

        result = p.transcribe(audio)
        assert result == "test transcript"
        assert captured_payload["url"] == DEFAULT_BASE_URL
        assert captured_payload["headers"]["Authorization"] == "Bearer sk-or-testkey123"
        assert captured_payload["headers"]["Content-Type"] == "application/json"
        assert captured_payload["timeout"] == 60.0

        payload = captured_payload["json"]
        assert payload["model"] == DEFAULT_MODEL
        audio_content = payload["messages"][0]["content"][1]
        assert audio_content["type"] == "input_audio"
        assert audio_content["input_audio"]["format"] == "wav"

        decoded = base64.b64decode(audio_content["input_audio"]["data"])
        assert len(decoded) > 0

    def test_transcribe_network_error(self, monkeypatch):
        p = _make_provider()
        audio = _make_audio_data()

        import httpx
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: (_ for _ in ()).throw(httpx.RequestError("connection failed")))

        with pytest.raises(ProviderError, match="request failed"):
            p.transcribe(audio)

    def test_no_hardcoded_defaults_in_provider(self):
        with pytest.raises(TypeError):
            OpenRouterMultimodalProvider(api_key="sk-or-test")
