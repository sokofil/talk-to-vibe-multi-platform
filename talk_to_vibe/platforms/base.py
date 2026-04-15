from abc import ABC, abstractmethod


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
    def paste_text(self, text: str, auto_enter: bool = False) -> None:
        ...

    @abstractmethod
    def play_success_sound(self) -> None:
        ...

    @abstractmethod
    def get_permission_help(self) -> list[str]:
        ...
