import pytest
from importlib import resources

from talk_to_vibe.providers.prompts import load_prompt, load_custom_prompt


class TestLoadPrompt:
    def test_loads_transcription_prompt(self):
        result = load_prompt("transcription")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Transcribe" in result

    def test_transcription_prompt_has_coding_context(self):
        result = load_prompt("transcription")
        assert "coding" in result.lower()
        assert "file paths" in result.lower()
        assert "forward slashes" in result.lower()

    def test_transcription_prompt_content(self):
        result = load_prompt("transcription")
        assert "cleaned-up text" in result
        assert "Remove filler words" in result or "Remove filler words and disfluencies" in result
        assert "punctuation" in result
        assert result.strip() == result

    def test_caching_returns_same_object(self):
        first = load_prompt("transcription")
        second = load_prompt("transcription")
        assert first is second

    def test_missing_prompt_raises(self):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_prompt("nonexistent")

    def test_prompt_is_loaded_via_package_resources(self):
        prompt_path = resources.files("talk_to_vibe.providers.prompts").joinpath("transcription.md")
        assert prompt_path.is_file()


class TestLoadCustomPrompt:
    def test_loads_custom_prompt(self, tmp_path):
        prompt_file = tmp_path / "custom.md"
        prompt_file.write_text("My custom prompt\n")
        result = load_custom_prompt(str(prompt_file))
        assert result == "My custom prompt"

    def test_strips_whitespace(self, tmp_path):
        prompt_file = tmp_path / "custom.md"
        prompt_file.write_text("  My prompt  \n\n")
        result = load_custom_prompt(str(prompt_file))
        assert result == "My prompt"

    def test_expands_tilde(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        prompt_file = tmp_path / "custom.md"
        prompt_file.write_text("Home prompt\n")
        result = load_custom_prompt("~/custom.md")
        assert result == "Home prompt"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_custom_prompt("/nonexistent/path/prompt.md")
