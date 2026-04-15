from pathlib import Path
from functools import lru_cache

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_custom_prompt(path_str: str) -> str:
    path = Path(path_str).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Custom prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()
