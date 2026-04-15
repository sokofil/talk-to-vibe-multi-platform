from pathlib import Path
from typing import Optional

import yaml

from talk_to_vibe.config.constants import CONFIG_DIR, CONFIG_FILE
from talk_to_vibe.config.models import (
    AppConfig,
    ProviderConfig,
    GroqConfig,
    OpenAIConfig,
    OpenAICompatibleConfig,
    OpenRouterConfig,
)
from talk_to_vibe.errors import ConfigError


def load_config(path: Optional[Path] = None) -> AppConfig:
    config_path = path or CONFIG_FILE
    if not config_path.exists():
        return AppConfig()
    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Expected dict at top level in {config_path}")
    return _dict_to_config(raw)


def save_config(config: AppConfig, path: Optional[Path] = None) -> None:
    config_path = path or CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = _config_to_yaml(config)
    config_path.write_text(content)
    try:
        config_path.chmod(0o600)
    except OSError:
        pass


def _dict_to_config(raw: dict) -> AppConfig:
    providers_raw = raw.get("providers", {})
    groq_raw = providers_raw.get("groq", {})
    openai_raw = providers_raw.get("openai", {})
    compat_raw = providers_raw.get("openai_compatible", {})
    openrouter_raw = providers_raw.get("openrouter", {})

    return AppConfig(
        provider=raw.get("provider", "groq"),
        ptt_key=raw.get("ptt_key", "alt_r"),
        auto_enter=raw.get("auto_enter", False),
        prompt_file=raw.get("prompt_file", ""),
        providers=ProviderConfig(
            groq=GroqConfig(**{k: v for k, v in (groq_raw or {}).items() if k in GroqConfig.__dataclass_fields__}),
            openai=OpenAIConfig(**{k: v for k, v in (openai_raw or {}).items() if k in OpenAIConfig.__dataclass_fields__}),
            openai_compatible=OpenAICompatibleConfig(**{k: v for k, v in (compat_raw or {}).items() if k in OpenAICompatibleConfig.__dataclass_fields__}),
            openrouter=OpenRouterConfig(**{k: v for k, v in (openrouter_raw or {}).items() if k in OpenRouterConfig.__dataclass_fields__}),
        ),
    )


def _config_to_yaml(config: AppConfig) -> str:
    lines = []
    lines.append(f"provider: {_yaml_val(config.provider)}")
    lines.append(f"ptt_key: {_yaml_val(config.ptt_key)}")
    lines.append(f"auto_enter: {_yaml_val(config.auto_enter)}")
    if config.prompt_file:
        lines.append(f"prompt_file: {_yaml_val(config.prompt_file)}")
    else:
        lines.append("# prompt_file: ~/my_prompt.md  # Override the bundled transcription prompt with a custom .md file")
    lines.append("")
    lines.append("providers:")
    lines.append("  groq:")
    lines.append(f"    api_key: {_yaml_val(config.providers.groq.api_key)}")
    lines.append(f"    model: {_yaml_val(config.providers.groq.model)}")
    lines.append("  openai:")
    if config.provider == "openai":
        lines.append(f"    api_key: {_yaml_val(config.providers.openai.api_key)}")
        lines.append(f"    model: {_yaml_val(config.providers.openai.model)}")
    else:
        lines.append(f"    # api_key: sk-...")
        lines.append(f"    # model: whisper-1")
    lines.append("  openai_compatible:")
    if config.provider == "openai_compatible":
        lines.append(f"    base_url: {_yaml_val(config.providers.openai_compatible.base_url)}")
        lines.append(f"    api_key: {_yaml_val(config.providers.openai_compatible.api_key)}")
        lines.append(f"    model: {_yaml_val(config.providers.openai_compatible.model)}")
    else:
        lines.append(f"    # base_url: http://localhost:8000/v1")
        lines.append(f"    # api_key: \"\"")
        lines.append(f"    # model: whisper-1")
    lines.append("  openrouter:")
    if config.provider == "openrouter":
        lines.append(f"    api_key: {_yaml_val(config.providers.openrouter.api_key)}")
        lines.append(f"    model: {_yaml_val(config.providers.openrouter.model)}")
        lines.append(f"    base_url: {_yaml_val(config.providers.openrouter.base_url)}")
    else:
        lines.append(f"    # api_key: sk-or-...")
        lines.append(f"    # model: google/gemini-3.1-flash-lite-preview")
        lines.append(f"    # base_url: https://openrouter.ai/api/v1/chat/completions")
    lines.append("")
    return "\n".join(lines) + "\n"


def _yaml_val(val) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str) and (not val or " " in val or ":" in val or "#" in val):
        return f'"{val}"'
    if isinstance(val, str):
        return val
    return str(val)
