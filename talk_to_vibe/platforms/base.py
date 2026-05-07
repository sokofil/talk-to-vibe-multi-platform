from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class PasteResult:
    full_text: str
    clipboard_restore_failed: bool = False
    clipboard_restore_reason: str = ""


class BasePlatform(ABC):
    @abstractmethod
    def get_key_map(self) -> dict[str, object]:
        ...

    @abstractmethod
    def get_key_display_names(self) -> dict[str, str]:
        ...

    @abstractmethod
    def get_default_ptt_key(self) -> str:
        ...

    @abstractmethod
    def parse_ptt_chord(self, chord_str: str) -> frozenset:
        ...

    @abstractmethod
    def get_chord_display_name(self, chord_str: str) -> str:
        ...

    @abstractmethod
    def is_modifier_only(self, chord_str: str) -> bool:
        ...

    @abstractmethod
    def paste_text(self, text: str, auto_enter: bool = False) -> PasteResult:
        ...

    def paste_text_stream(self, chunks: Iterable[str], auto_enter: bool = False) -> PasteResult:
        """Paste a stream of text pieces, returning the joined full text.

        Default implementation buffers everything and calls paste_text once.
        Platforms that benefit from progressive feedback should override this.
        """
        parts: list[str] = []
        for chunk in chunks:
            piece = chunk.strip() if chunk else ""
            if piece:
                parts.append(piece)
        full_text = " ".join(parts).strip()
        if full_text:
            return self.paste_text(full_text, auto_enter=auto_enter)
        return PasteResult(full_text="")

    @abstractmethod
    def play_success_sound(self) -> None:
        ...

    @abstractmethod
    def get_permission_help(self) -> list[str]:
        ...

    def get_global_key_permission_help(self) -> list[str]:
        return self.get_permission_help()

    def get_microphone_permission_help(self) -> list[str]:
        return self.get_permission_help()

    def has_global_key_access(self) -> bool:
        return True

    def request_global_key_access(self) -> bool:
        return self.has_global_key_access()

    def get_global_key_access_status(self) -> dict[str, bool]:
        return {"global_key_access": self.has_global_key_access()}

    def normalize_listener_key(self, key: object) -> object:
        return key

    def describe_listener_key(self, key: object) -> str:
        return repr(key)

    def build_listener_kwargs(self, logger, debug_key_events: bool = False) -> dict:
        return {}
