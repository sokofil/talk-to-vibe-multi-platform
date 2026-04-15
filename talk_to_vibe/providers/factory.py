from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.providers.groq_whisper import GroqWhisperProvider
from talk_to_vibe.providers.openai_whisper import OpenAIWhisperProvider
from talk_to_vibe.providers.openai_compatible import OpenAICompatibleProvider
from talk_to_vibe.providers.openrouter_multimodal import OpenRouterMultimodalProvider
from talk_to_vibe.config.models import AppConfig
from talk_to_vibe.errors import ProviderError, ProviderAuthError

PROVIDER_REGISTRY = {
    "groq": GroqWhisperProvider,
    "openai": OpenAIWhisperProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "openrouter": OpenRouterMultimodalProvider,
}


def create_provider(config: AppConfig) -> BaseSTTProvider:
    provider_name = config.provider
    cls = PROVIDER_REGISTRY.get(provider_name)
    if cls is None:
        raise ProviderError(f"Unknown provider: {provider_name}")

    if provider_name == "groq":
        if not config.providers.groq.api_key:
            raise ProviderAuthError("Groq API key not found. Run: ./run_ttv.sh --setup")
        return cls(api_key=config.providers.groq.api_key, model=config.providers.groq.model)

    elif provider_name == "openai":
        if not config.providers.openai.api_key:
            raise ProviderAuthError("OpenAI API key not found. Run: ./run_ttv.sh --setup")
        return cls(api_key=config.providers.openai.api_key, model=config.providers.openai.model)

    elif provider_name == "openai_compatible":
        if not config.providers.openai_compatible.base_url:
            raise ProviderAuthError("Base URL not found. Run: ./run_ttv.sh --setup")
        return cls(
            base_url=config.providers.openai_compatible.base_url,
            api_key=config.providers.openai_compatible.api_key,
            model=config.providers.openai_compatible.model,
        )

    elif provider_name == "openrouter":
        if not config.providers.openrouter.api_key:
            raise ProviderAuthError("OpenRouter API key not found. Run: ./run_ttv.sh --setup")
        return cls(
            api_key=config.providers.openrouter.api_key,
            model=config.providers.openrouter.model,
            base_url=config.providers.openrouter.base_url,
            prompt_file=config.prompt_file,
        )

    raise ProviderError(f"Unhandled provider: {provider_name}")
