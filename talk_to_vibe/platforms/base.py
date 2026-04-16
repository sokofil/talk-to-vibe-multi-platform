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
