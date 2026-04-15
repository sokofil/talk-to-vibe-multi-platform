import sys
import pytest
from unittest.mock import MagicMock, patch

from talk_to_vibe.cli import main
from talk_to_vibe.config.models import AppConfig, ProviderConfig, GroqConfig, OpenAIConfig


class TestCLI:
    def test_setup_flag_runs_wizard(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["talk-to-vibe", "--setup", "--terminal"])
        cfg = AppConfig(provider="groq", providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")))
        mock_wizard = MagicMock(return_value=cfg)
        monkeypatch.setattr("talk_to_vibe.cli.run_wizard", mock_wizard)
        mock_app_class = MagicMock()
        monkeypatch.setattr("talk_to_vibe.app.TalkToVibe", mock_app_class)

        try:
            main()
        except SystemExit:
            pass

        assert mock_app_class.called

    def test_missing_key_prompts_setup(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["talk-to-vibe", "--terminal"])
        monkeypatch.setattr("talk_to_vibe.cli.load_config", lambda: AppConfig(provider="groq"))

        with pytest.raises(SystemExit):
            main()

    def test_provider_override(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["talk-to-vibe", "--provider", "groq", "--terminal"])
        cfg = AppConfig(provider="openai", providers=ProviderConfig(
            groq=GroqConfig(api_key="gsk_test"),
            openai=OpenAIConfig(api_key="sk_test"),
        ))
        monkeypatch.setattr("talk_to_vibe.cli.load_config", lambda: cfg)
        mock_app_class = MagicMock()
        monkeypatch.setattr("talk_to_vibe.app.TalkToVibe", mock_app_class)

        try:
            main()
        except SystemExit:
            pass

        assert mock_app_class.called

    def test_terminal_flag_forces_terminal_mode(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["talk-to-vibe", "--terminal"])
        cfg = AppConfig(provider="groq", providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")))
        monkeypatch.setattr("talk_to_vibe.cli.load_config", lambda: cfg)
        mock_app_class = MagicMock()
        monkeypatch.setattr("talk_to_vibe.app.TalkToVibe", mock_app_class)

        try:
            main()
        except SystemExit:
            pass

        assert mock_app_class.called

    def test_menubar_flag_on_macos(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["talk-to-vibe", "--menubar"])
        monkeypatch.setattr("sys.platform", "darwin")
        cfg = AppConfig(provider="groq", providers=ProviderConfig(groq=GroqConfig(api_key="gsk_test")))
        monkeypatch.setattr("talk_to_vibe.cli.load_config", lambda: cfg)
        mock_menubar_class = MagicMock()
        monkeypatch.setattr("talk_to_vibe.menubar.TalkToVibeMenuBar", mock_menubar_class)

        try:
            main()
        except SystemExit:
            pass

        assert mock_menubar_class.called
