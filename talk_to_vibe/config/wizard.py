from talk_to_vibe.config.constants import SUPPORTED_PROVIDERS
from talk_to_vibe.config.loader import load_config, save_config
from talk_to_vibe.config.models import AppConfig, GroqConfig, OpenAICompatibleConfig, OpenRouterConfig
from talk_to_vibe.errors import ConfigError


def _input_safe(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n   Cancelled.")
        raise SystemExit(0)


def _ask_api_key(label: str, url: str, prefix: str | None = None) -> str:
    print(f"   Get your key at: {url}")
    while True:
        key = _input_safe("   Enter API key: ")
        if not key:
            print("   ⚠️  API key cannot be empty. Try again.")
            continue
        if prefix and not key.startswith(prefix):
            print(f"   ⚠️  Expected key starting with '{prefix}'. Are you sure? (y/n) ", end="")
            if _input_safe("").lower() != "y":
                continue
        return key


def run_wizard(config: AppConfig | None = None, force: bool = False) -> AppConfig:
    if config is None:
        config = load_config()

    if not force and config.providers.groq.api_key:
        return config

    print("\n🔧 STT Provider Setup\n")
    print("   Choose your Speech-to-Text provider:\n")

    display_names = {
        "groq": "Groq — Whisper transcription (free, fast)",
        "openai": "OpenAI — Whisper transcription (paid)",
        "openai_compatible": "OpenAI-Compatible — Whisper transcription (self-hosted)",
        "openrouter": "OpenRouter — Multimodal chat models (Gemini, etc.)",
    }

    for i, key in enumerate(SUPPORTED_PROVIDERS, 1):
        print(f"   {i}) {display_names.get(key, key)}")

    print()
    while True:
        choice = _input_safe(f"   Select provider [1-{len(SUPPORTED_PROVIDERS)}]: ")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(SUPPORTED_PROVIDERS):
                break
        except ValueError:
            pass
        print(f"   ⚠️  Enter a number between 1 and {len(SUPPORTED_PROVIDERS)}")

    provider = SUPPORTED_PROVIDERS[idx]
    config.provider = provider
    print(f"\n   Selected: {display_names.get(provider, provider)}\n")

    if provider == "groq":
        config.providers.groq.api_key = _ask_api_key(
            "Groq", "https://console.groq.com/keys", "gsk_"
        )
        model = _input_safe(f"   Model name (default: {config.providers.groq.model}): ")
        if model:
            config.providers.groq.model = model

    elif provider == "openai":
        config.providers.openai.api_key = _ask_api_key(
            "OpenAI", "https://platform.openai.com/api-keys", "sk-"
        )
        model = _input_safe(f"   Model name (default: {config.providers.openai.model}): ")
        if model:
            config.providers.openai.model = model

    elif provider == "openai_compatible":
        print("   Configure your OpenAI-compatible endpoint:\n")
        base_url = _input_safe("   Base URL (e.g. http://localhost:8000/v1): ")
        if not base_url:
            raise ConfigError("Base URL is required for openai_compatible provider.")
        config.providers.openai_compatible.base_url = base_url
        config.providers.openai_compatible.api_key = _input_safe(
            "   API key (leave empty if not needed): "
        )
        model = _input_safe(f"   Model name (default: {config.providers.openai_compatible.model}): ")
        if model:
            config.providers.openai_compatible.model = model

    elif provider == "openrouter":
        config.providers.openrouter.api_key = _ask_api_key(
            "OpenRouter", "https://openrouter.ai/settings/keys", "sk-or-"
        )
        model = _input_safe(f"   Model name (default: {config.providers.openrouter.model}): ")
        if model:
            config.providers.openrouter.model = model
        base_url = _input_safe(f"   Base URL (default: {config.providers.openrouter.base_url}): ")
        if base_url:
            config.providers.openrouter.base_url = base_url

    _configure_ptt_key(config)
    _configure_auto_enter(config)
    _configure_prompt_file(config)

    save_config(config)
    print("   ✅ Saved to ~/.talktovibe/config.yaml\n")
    return config


def _configure_ptt_key(config: AppConfig) -> None:
    from talk_to_vibe.platforms.detect import get_platform

    platform = get_platform()
    key_map = platform.get_key_map()
    key_display = platform.get_key_display_names()
    key_list = list(key_map.keys())

    print("\n🎹 Push-to-Talk Key Setup\n")
    current_key = config.ptt_key
    current_display = platform.get_chord_display_name(current_key)
    print(f"   Current: {current_display}\n")
    print("   Choose a preset key or type a custom chord:\n")
    for i, key in enumerate(key_list, 1):
        label = key_display.get(key, key)
        print(f"   {i}) {label}")

    print()
    print("   Or type a chord like: ctrl+alt_r  or  ctrl+shift_l+f18")
    print()
    while True:
        choice = _input_safe(f"   Select PTT key [1-{len(key_list)}] or type chord (Enter = keep current): ")
        if not choice:
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(key_list):
                selected = key_list[idx]
                config.ptt_key = selected
                print(f"   Selected: {key_display.get(selected, selected)}")
                _warn_if_modifier_only(platform, selected)
                break
        except ValueError:
            pass

        try:
            platform.parse_ptt_chord(choice)
            config.ptt_key = choice
            print(f"   Selected chord: {platform.get_chord_display_name(choice)}")
            _warn_if_modifier_only(platform, choice)
            break
        except Exception as e:
            print(f"   ⚠️  Invalid chord: {e}")
            continue
        print(f"   ⚠️  Enter a number between 1 and {len(key_list)}, or a chord like ctrl+alt_r")


def _warn_if_modifier_only(platform, chord_str: str) -> None:
    if platform.is_modifier_only(chord_str):
        print("   ⚠️  Warning: modifier-only keys can conflict with system shortcuts.")
        print("      Consider using an F-key (F18/F19/F20) or adding a chord like ctrl+f18.")


def _configure_auto_enter(config: AppConfig) -> None:
    print("\n⏎  Auto-Enter Setup\n")
    current_label = "ON" if config.auto_enter else "OFF"
    print(f"   Auto-Enter sends Enter key after pasting (current: {current_label})")
    print()
    print("   1) OFF — paste only (default)")
    print("   2) ON  — paste + Enter")
    print()
    while True:
        choice = _input_safe("   Select [1-2] (Enter = keep current): ")
        if not choice:
            break
        if choice == "1":
            config.auto_enter = False
            print("   Selected: OFF")
            break
        elif choice == "2":
            config.auto_enter = True
            print("   Selected: ON")
            break
        print("   ⚠️  Enter 1 or 2")


def _configure_prompt_file(config: AppConfig) -> None:
    print("\n📄 Custom Prompt Setup\n")
    print("   A transcription prompt tells the LLM how to format output.")
    print("   By default, a coding-aware prompt is bundled with Talk to Vibe.")
    print("   You can provide your own .md file to override it.\n")
    current = config.prompt_file or "(none)"
    print(f"   Current custom prompt: {current}")
    print()
    path = _input_safe("   Path to custom prompt .md (Enter = use default): ")
    if path:
        config.prompt_file = path
        print(f"   Custom prompt set: {path}")
    else:
        config.prompt_file = ""
        print("   Using default bundled prompt")
