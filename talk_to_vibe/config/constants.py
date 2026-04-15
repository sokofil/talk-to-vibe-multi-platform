from pathlib import Path

CONFIG_DIR = Path.home() / ".talktovibe"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_PROVIDER = "groq"
DEFAULT_PTT_KEY = "alt_r"

SUPPORTED_PROVIDERS = ["groq", "openai", "openai_compatible", "openrouter"]
