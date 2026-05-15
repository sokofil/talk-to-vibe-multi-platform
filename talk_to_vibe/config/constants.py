from pathlib import Path

CONFIG_DIR = Path.home() / ".talktovibe"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_PROVIDER = "groq"
DEFAULT_PTT_KEY = "ctrl+9"

SUPPORTED_PROVIDERS = ["groq", "openai", "openai_compatible", "openrouter", "local_whisper", "mlx_whisper"]
