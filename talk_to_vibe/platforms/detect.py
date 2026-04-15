import sys

from talk_to_vibe.platforms.base import BasePlatform
from talk_to_vibe.errors import PlatformNotSupportedError


def get_platform() -> BasePlatform:
    if sys.platform == "darwin":
        from talk_to_vibe.platforms.macos import MacOSPlatform
        return MacOSPlatform()
    elif sys.platform.startswith("linux"):
        from talk_to_vibe.platforms.linux import LinuxPlatform
        return LinuxPlatform()
    elif sys.platform == "win32":
        from talk_to_vibe.platforms.windows import WindowsPlatform
        return WindowsPlatform()
    raise PlatformNotSupportedError(f"Unsupported platform: {sys.platform}")
