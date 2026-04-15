class TalkToVibeError(Exception):
    pass


class ConfigError(TalkToVibeError):
    pass


class ProviderError(TalkToVibeError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


class PlatformError(TalkToVibeError):
    pass


class PlatformNotSupportedError(PlatformError):
    pass
