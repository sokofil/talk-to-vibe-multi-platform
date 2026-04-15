from dataclasses import dataclass, field

from talk_to_vibe.config.constants import DEFAULT_PROVIDER, DEFAULT_PTT_KEY


@dataclass
class GroqConfig:
    api_key: str = ""
    model: str = "whisper-large-v3-turbo"


@dataclass
class OpenAIConfig:
    api_key: str = ""
    model: str = "whisper-1"


@dataclass
class OpenAICompatibleConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "whisper-1"


@dataclass
class OpenRouterConfig:
    api_key: str = ""
    model: str = "google/gemini-3.1-flash-lite-preview"
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class ProviderConfig:
    groq: GroqConfig = field(default_factory=GroqConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    openai_compatible: OpenAICompatibleConfig = field(default_factory=OpenAICompatibleConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)


@dataclass
class AppConfig:
    provider: str = DEFAULT_PROVIDER
    ptt_key: str = DEFAULT_PTT_KEY
    auto_enter: bool = False
    prompt_file: str = ""
    providers: ProviderConfig = field(default_factory=ProviderConfig)

    def validate(self) -> list[str]:
        errors = []
        if self.provider not in ("groq", "openai", "openai_compatible", "openrouter"):
            errors.append(f"Unknown provider: {self.provider}")
        if self.provider == "groq":
            if not self.providers.groq.api_key:
                errors.append("Groq API key is required when provider is 'groq'")
            if not self.providers.groq.model:
                errors.append("Groq model is required when provider is 'groq'")
        if self.provider == "openai":
            if not self.providers.openai.api_key:
                errors.append("OpenAI API key is required when provider is 'openai'")
            if not self.providers.openai.model:
                errors.append("OpenAI model is required when provider is 'openai'")
        if self.provider == "openai_compatible":
            if not self.providers.openai_compatible.base_url:
                errors.append("Base URL is required when provider is 'openai_compatible'")
            if not self.providers.openai_compatible.model:
                errors.append("Model is required when provider is 'openai_compatible'")
        if self.provider == "openrouter":
            if not self.providers.openrouter.api_key:
                errors.append("OpenRouter API key is required when provider is 'openrouter'")
            if not self.providers.openrouter.model:
                errors.append("OpenRouter model is required when provider is 'openrouter'")
            if not self.providers.openrouter.base_url:
                errors.append("OpenRouter base URL is required when provider is 'openrouter'")
        return errors
