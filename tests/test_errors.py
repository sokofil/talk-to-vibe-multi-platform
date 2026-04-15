from talk_to_vibe.errors import (
    TalkToVibeError,
    ConfigError,
    ProviderError,
    ProviderAuthError,
    ProviderResponseError,
    PlatformError,
    PlatformNotSupportedError,
)


class TestErrorHierarchy:
    def test_config_error_is_base(self):
        assert issubclass(ConfigError, TalkToVibeError)

    def test_provider_error_is_base(self):
        assert issubclass(ProviderError, TalkToVibeError)

    def test_provider_auth_is_provider(self):
        assert issubclass(ProviderAuthError, ProviderError)

    def test_provider_response_is_provider(self):
        assert issubclass(ProviderResponseError, ProviderError)

    def test_platform_error_is_base(self):
        assert issubclass(PlatformError, TalkToVibeError)

    def test_platform_not_supported_is_platform(self):
        assert issubclass(PlatformNotSupportedError, PlatformError)
