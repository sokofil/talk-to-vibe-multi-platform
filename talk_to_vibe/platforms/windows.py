from talk_to_vibe.platforms.base import BasePlatform
from talk_to_vibe.errors import PlatformNotSupportedError


class WindowsPlatform(BasePlatform):
    def get_key_map(self) -> dict[str, object]:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def get_key_display_names(self) -> dict[str, str]:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def get_default_ptt_key(self) -> str:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def parse_ptt_chord(self, chord_str: str) -> frozenset:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def get_chord_display_name(self, chord_str: str) -> str:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def is_modifier_only(self, chord_str: str) -> bool:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def paste_text(self, text: str, auto_enter: bool = False) -> None:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def play_success_sound(self) -> None:
        raise PlatformNotSupportedError("Windows is not yet supported")

    def get_permission_help(self) -> list[str]:
        raise PlatformNotSupportedError("Windows is not yet supported")
