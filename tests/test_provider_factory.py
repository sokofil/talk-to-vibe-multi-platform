import pytest

from talk_to_vibe.providers.factory import create_provider
from talk_to_vibe.providers.openrouter_multimodal import OpenRouterMultimodalProvider
from talk_to_vibe.providers.openai_compatible import OpenAICompatibleProvider
from talk_to_vibe.providers.groq_whisper import GroqWhisperProvider
from talk_to_vibe.providers.openai_whisper import OpenAIWhisperProvider
from talk_to_vibe.config.models import AppConfig, ProviderConfig, GroqConfig, OpenAIConfig, OpenAICompatibleConfig, OpenRouterConfig
from talk_to_vibe.errors import ProviderError, ProviderAuthError


class TestCreateProvider:
    def test_groq_provider(self):
        cfg = AppConfig(provider="groq", providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")))
        p = create_provider(cfg)
        assert isinstance(p, GroqWhisperProvider)
        assert p.provider_name == "Groq"
        assert p.model == "whisper-large-v3-turbo"

    def test_openai_provider(self):
        cfg = AppConfig(provider="openai", providers=ProviderConfig(openai=OpenAIConfig(api_key="sk_test")))
        p = create_provider(cfg)
        assert isinstance(p, OpenAIWhisperProvider)
        assert p.provider_name == "OpenAI"
        assert p.model == "whisper-1"

    def test_openai_compatible_provider(self):
        cfg = AppConfig(provider="openai_compatible", providers=ProviderConfig(openai_compatible=OpenAICompatibleConfig(base_url="http://localhost:8000/v1", api_key="key")))
        p = create_provider(cfg)
        assert isinstance(p, OpenAICompatibleProvider)
        assert p.provider_name == "OpenAI-Compatible"
        assert p.model == "whisper-1"
        assert str(p.client.base_url).rstrip("/") == "http://localhost:8000/v1"

    def test_openrouter_provider(self):
        cfg = AppConfig(provider="openrouter", providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-test")))
        p = create_provider(cfg)
        assert isinstance(p, OpenRouterMultimodalProvider)
        assert p.provider_name == "OpenRouter"
        assert p.model == "google/gemini-3.1-flash-lite-preview"
        assert p.base_url == "https://openrouter.ai/api/v1/chat/completions"

    def test_unknown_provider_raises(self):
        cfg = AppConfig(provider="bogus")
        with pytest.raises(ProviderError, match="Unknown provider"):
            create_provider(cfg)

    def test_missing_groq_key_raises(self):
        cfg = AppConfig(provider="groq")
        with pytest.raises(ProviderAuthError, match="Groq API key"):
            create_provider(cfg)

    def test_missing_openai_key_raises(self):
        cfg = AppConfig(provider="openai")
        with pytest.raises(ProviderAuthError, match="OpenAI API key"):
            create_provider(cfg)

    def test_missing_openai_compatible_base_url_raises(self):
        cfg = AppConfig(provider="openai_compatible")
        with pytest.raises(ProviderAuthError, match="Base URL"):
            create_provider(cfg)

    def test_missing_openrouter_key_raises(self):
        cfg = AppConfig(provider="openrouter")
        with pytest.raises(ProviderAuthError, match="OpenRouter API key"):
            create_provider(cfg)

    def test_openrouter_custom_model(self):
        cfg = AppConfig(provider="openrouter", providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-test", model="google/gemini-2.5-flash")))
        p = create_provider(cfg)
        assert p.model == "google/gemini-2.5-flash"

    def test_openrouter_custom_base_url(self):
        cfg = AppConfig(provider="openrouter", providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-test", base_url="https://custom.example.com/v1/chat/completions")))
        p = create_provider(cfg)
        assert p.base_url == "https://custom.example.com/v1/chat/completions"
