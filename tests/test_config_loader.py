import pytest
import yaml

from talk_to_vibe.config.loader import load_config, save_config, _config_to_yaml, _dict_to_config
from talk_to_vibe.config.models import AppConfig, ProviderConfig, GroqConfig, OpenAIConfig, OpenAICompatibleConfig, OpenRouterConfig
from talk_to_vibe.errors import ConfigError


class TestAppConfigDefaults:
    def test_default_provider_is_groq(self):
        cfg = AppConfig()
        assert cfg.provider == "groq"

    def test_default_ptt_key_is_alt_r(self):
        cfg = AppConfig()
        assert cfg.ptt_key == "alt_r"

    def test_default_auto_enter_is_false(self):
        cfg = AppConfig()
        assert cfg.auto_enter is False

    def test_default_prompt_file_is_empty(self):
        cfg = AppConfig()
        assert cfg.prompt_file == ""

    def test_default_provider_configs_exist(self):
        cfg = AppConfig()
        assert isinstance(cfg.providers.groq, GroqConfig)
        assert isinstance(cfg.providers.openai, OpenAIConfig)
        assert isinstance(cfg.providers.openai_compatible, OpenAICompatibleConfig)
        assert isinstance(cfg.providers.openrouter, OpenRouterConfig)

    def test_default_models_are_in_config(self):
        cfg = AppConfig()
        assert cfg.providers.groq.model == "whisper-large-v3-turbo"
        assert cfg.providers.openai.model == "whisper-1"
        assert cfg.providers.openai_compatible.model == "whisper-1"
        assert cfg.providers.openrouter.model == "google/gemini-3.1-flash-lite-preview"

    def test_default_base_urls_are_in_config(self):
        cfg = AppConfig()
        assert cfg.providers.openrouter.base_url == "https://openrouter.ai/api/v1/chat/completions"


class TestAppConfigValidation:
    def test_valid_groq_config(self):
        cfg = AppConfig(provider="groq", providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")))
        assert cfg.validate() == []

    def test_valid_openai_config(self):
        cfg = AppConfig(provider="openai", providers=ProviderConfig(openai=OpenAIConfig(api_key="sk_test")))
        assert cfg.validate() == []

    def test_valid_openai_compatible_config(self):
        cfg = AppConfig(provider="openai_compatible", providers=ProviderConfig(openai_compatible=OpenAICompatibleConfig(base_url="http://localhost:8000/v1")))
        assert cfg.validate() == []

    def test_valid_openrouter_config(self):
        cfg = AppConfig(provider="openrouter", providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-test")))
        assert cfg.validate() == []

    def test_missing_groq_api_key(self):
        cfg = AppConfig(provider="groq")
        errors = cfg.validate()
        assert any("Groq API key" in e for e in errors)

    def test_missing_openai_api_key(self):
        cfg = AppConfig(provider="openai")
        errors = cfg.validate()
        assert any("OpenAI API key" in e for e in errors)

    def test_missing_openai_compatible_base_url(self):
        cfg = AppConfig(provider="openai_compatible")
        errors = cfg.validate()
        assert any("Base URL" in e for e in errors)

    def test_missing_openrouter_api_key(self):
        cfg = AppConfig(provider="openrouter")
        errors = cfg.validate()
        assert any("OpenRouter API key" in e for e in errors)

    def test_unknown_provider(self):
        cfg = AppConfig(provider="bogus")
        errors = cfg.validate()
        assert any("Unknown provider" in e for e in errors)

    def test_missing_openrouter_model(self):
        cfg = AppConfig(provider="openrouter", providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-test", model="")))
        errors = cfg.validate()
        assert any("OpenRouter model" in e for e in errors)

    def test_missing_openrouter_base_url(self):
        cfg = AppConfig(provider="openrouter", providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-test", base_url="")))
        errors = cfg.validate()
        assert any("OpenRouter base URL" in e for e in errors)


class TestLoadConfig:
    def test_load_missing_file_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.provider == "groq"
        assert cfg.ptt_key == "alt_r"
        assert cfg.prompt_file == ""

    def test_load_valid_yaml(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump({
            "provider": "openrouter",
            "ptt_key": "f19",
            "auto_enter": True,
            "providers": {
                "openrouter": {"api_key": "sk-or-test123", "model": "google/gemini-3.1-flash-lite-preview", "base_url": "https://openrouter.ai/api/v1/chat/completions"},
            },
        }))
        cfg = load_config(p)
        assert cfg.provider == "openrouter"
        assert cfg.ptt_key == "f19"
        assert cfg.auto_enter is True
        assert cfg.providers.openrouter.api_key == "sk-or-test123"

    def test_load_prompt_file(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump({
            "provider": "groq",
            "prompt_file": "~/my_prompt.md",
            "providers": {"groq": {"api_key": "gsk_test"}},
        }))
        cfg = load_config(p)
        assert cfg.prompt_file == "~/my_prompt.md"

    def test_load_invalid_yaml_raises(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("{{{{invalid yaml")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(p)

    def test_load_non_dict_yaml_raises(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("42")
        with pytest.raises(ConfigError, match="Expected dict"):
            load_config(p)

    def test_load_partial_config_fills_defaults(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump({"provider": "openai"}))
        cfg = load_config(p)
        assert cfg.provider == "openai"
        assert cfg.ptt_key == "alt_r"
        assert cfg.auto_enter is False
        assert cfg.prompt_file == ""
        assert cfg.providers.openai.model == "whisper-1"


class TestSaveConfig:
    def test_save_creates_file(self, tmp_path):
        p = tmp_path / "sub" / "config.yaml"
        cfg = AppConfig(provider="openrouter", ptt_key="f19", auto_enter=True, providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-test")))
        save_config(cfg, path=p)
        assert p.exists()
        raw = yaml.safe_load(p.read_text())
        assert raw["provider"] == "openrouter"
        assert raw["ptt_key"] == "f19"
        assert raw["auto_enter"] is True

    def test_roundtrip_save_load(self, tmp_path):
        p = tmp_path / "config.yaml"
        original = AppConfig(
            provider="groq",
            ptt_key="cmd_r",
            auto_enter=True,
            providers=ProviderConfig(
                groq=GroqConfig(api_key="gsk_abc123", model="whisper-large-v3"),
            ),
        )
        save_config(original, path=p)
        loaded = load_config(p)
        assert loaded.provider == original.provider
        assert loaded.ptt_key == original.ptt_key
        assert loaded.auto_enter == original.auto_enter
        assert loaded.providers.groq.api_key == original.providers.groq.api_key
        assert loaded.providers.groq.model == original.providers.groq.model

    def test_roundtrip_prompt_file(self, tmp_path):
        p = tmp_path / "config.yaml"
        original = AppConfig(
            provider="groq",
            prompt_file="~/my_prompt.md",
            providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")),
        )
        save_config(original, path=p)
        loaded = load_config(p)
        assert loaded.prompt_file == "~/my_prompt.md"

    def test_saved_yaml_has_commented_prompt_file_when_empty(self, tmp_path):
        p = tmp_path / "config.yaml"
        cfg = AppConfig(provider="groq", providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")))
        save_config(cfg, path=p)
        content = p.read_text()
        assert "# prompt_file:" in content

    def test_saved_yaml_has_active_prompt_file_when_set(self, tmp_path):
        p = tmp_path / "config.yaml"
        cfg = AppConfig(
            provider="groq",
            prompt_file="~/my_prompt.md",
            providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")),
        )
        save_config(cfg, path=p)
        content = p.read_text()
        assert "prompt_file: ~/my_prompt.md" in content
        assert "# prompt_file:" not in content

    def test_saved_yaml_has_commented_inactive_providers(self, tmp_path):
        p = tmp_path / "config.yaml"
        cfg = AppConfig(provider="groq", providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")))
        save_config(cfg, path=p)
        content = p.read_text()
        assert "# api_key: sk-or-..." in content
        assert "# base_url: http://localhost:8000/v1" in content
        assert "api_key: gsk_test" in content

    def test_saved_yaml_has_active_provider_uncommented(self, tmp_path):
        p = tmp_path / "config.yaml"
        cfg = AppConfig(
            provider="openrouter",
            providers=ProviderConfig(openrouter=OpenRouterConfig(api_key="sk-or-real")),
        )
        save_config(cfg, path=p)
        content = p.read_text()
        lines = content.split("\n")
        openrouter_section = False
        for line in lines:
            if "openrouter:" in line and not line.strip().startswith("#"):
                openrouter_section = True
            if openrouter_section and "api_key:" in line and not line.strip().startswith("#"):
                assert "sk-or-real" in line
                break


class TestConfigToYaml:
    def test_includes_all_provider_sections(self):
        cfg = AppConfig()
        result = _config_to_yaml(cfg)
        assert "groq:" in result
        assert "openai:" in result
        assert "openai_compatible:" in result
        assert "openrouter:" in result

    def test_includes_prompt_file(self):
        cfg = AppConfig(prompt_file="/path/to/prompt.md")
        result = _config_to_yaml(cfg)
        assert "prompt_file: /path/to/prompt.md" in result

    def test_commented_prompt_file_when_empty(self):
        cfg = AppConfig(prompt_file="")
        result = _config_to_yaml(cfg)
        assert "# prompt_file:" in result


class TestDictToConfig:
    def test_ignores_extra_keys(self):
        raw = {
            "provider": "groq",
            "ptt_key": "alt_r",
            "auto_enter": False,
            "prompt_file": "",
            "providers": {
                "groq": {"api_key": "gsk_test", "model": "whisper-large-v3-turbo", "extra": "ignored"},
            },
        }
        cfg = _dict_to_config(raw)
        assert cfg.providers.groq.api_key == "gsk_test"
