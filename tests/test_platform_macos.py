from unittest.mock import patch, MagicMock
import pytest

from talk_to_vibe.platforms.macos import MacOSPlatform
from talk_to_vibe.platforms.linux import LinuxPlatform
from talk_to_vibe.platforms.windows import WindowsPlatform
from talk_to_vibe.errors import PlatformNotSupportedError, PlatformError


class TestMacOSPlatform:
    def test_has_global_key_access(self):
        p = MacOSPlatform()
        with patch.object(MacOSPlatform, "has_accessibility_access", return_value=True), \
             patch.object(MacOSPlatform, "has_listen_event_access", return_value=True):
            assert p.has_global_key_access() is True

    def test_get_global_key_access_status(self):
        p = MacOSPlatform()
        with patch.object(MacOSPlatform, "has_accessibility_access", return_value=True), \
             patch.object(MacOSPlatform, "has_listen_event_access", return_value=False):
            assert p.get_global_key_access_status() == {
                "accessibility": True,
                "listen_event": False,
            }

    def test_request_global_key_access(self):
        p = MacOSPlatform()
        with patch("Quartz.CGRequestListenEventAccess", return_value=True), \
             patch.object(MacOSPlatform, "request_accessibility_access", return_value=True):
            assert p.request_global_key_access() is True

    def test_has_accessibility_access(self):
        p = MacOSPlatform()
        fake_bundle = object()
        functions = {"AXIsProcessTrusted": lambda: True}
        with patch("objc.loadBundle", return_value=fake_bundle), \
             patch("objc.loadBundleFunctions", side_effect=lambda bundle, namespace, descriptors: namespace.update(functions)):
            assert p.has_accessibility_access() is True

    def test_request_accessibility_access(self):
        p = MacOSPlatform()
        fake_bundle = object()
        captured = {}

        def load_functions(bundle, namespace, descriptors):
            namespace.update({"AXIsProcessTrustedWithOptions": lambda options: captured.setdefault("options", options) or True})

        with patch("objc.loadBundle", return_value=fake_bundle), \
             patch("objc.loadBundleFunctions", side_effect=load_functions):
            assert p.request_accessibility_access() is True
        assert captured["options"]["AXTrustedCheckOptionPrompt"] is True

    def test_get_key_map_has_expected_keys(self):
        p = MacOSPlatform()
        key_map = p.get_key_map()
        assert "1" in key_map
        assert "f18" in key_map
        assert "f9" in key_map
        assert "alt_r" in key_map
        assert "alt_l" in key_map
        assert "cmd_r" in key_map
        assert "ctrl_r" in key_map
        assert "ctrl_l" in key_map
        assert "shift_r" in key_map

    def test_normalize_listener_key_maps_side_specific_modifiers_to_generic(self):
        p = MacOSPlatform()
        from pynput import keyboard

        assert p.normalize_listener_key(keyboard.Key.alt_l) == keyboard.Key.alt
        assert p.normalize_listener_key(keyboard.Key.alt_r) == keyboard.Key.alt
        assert p.normalize_listener_key(keyboard.Key.cmd_l) == keyboard.Key.cmd

    def test_normalize_listener_key_maps_characters_to_stable_vk_keycodes(self):
        p = MacOSPlatform()
        from pynput import keyboard

        assert p.normalize_listener_key(keyboard.KeyCode.from_char("1", vk=18)) == keyboard.KeyCode.from_vk(18)
        assert p.normalize_listener_key(keyboard.KeyCode.from_char("!", vk=18)) == keyboard.KeyCode.from_vk(18)

    def test_describe_listener_key_shows_normalization(self):
        p = MacOSPlatform()
        from pynput import keyboard

        description = p.describe_listener_key(keyboard.Key.alt_l)
        assert "alt" in description

    def test_build_listener_kwargs_adds_darwin_intercept(self):
        p = MacOSPlatform()
        logger = MagicMock()
        kwargs = p.build_listener_kwargs(logger)
        assert "darwin_intercept" in kwargs
        assert callable(kwargs["darwin_intercept"])

    def test_build_listener_kwargs_respects_debug_flag(self):
        p = MacOSPlatform()
        logger = MagicMock()

        with patch("Quartz.CGEventGetIntegerValueField", return_value=25), \
             patch("Quartz.CGEventGetFlags", return_value=256), \
             patch("Quartz.kCGKeyboardEventKeycode", 9):
            kwargs = p.build_listener_kwargs(logger, debug_key_events=False)
            kwargs["darwin_intercept"](10, object())

        logger.info.assert_not_called()

    def test_get_key_display_names(self):
        p = MacOSPlatform()
        names = p.get_key_display_names()
        assert "alt_r" in names
        assert "Option" in names["alt_r"]

    def test_default_ptt_key(self):
        p = MacOSPlatform()
        assert p.get_default_ptt_key() == "ctrl+9"

    def test_permission_help(self):
        p = MacOSPlatform()
        help_lines = p.get_permission_help()
        assert len(help_lines) >= 3
        assert any("Input Monitoring" in line for line in help_lines)
        assert any("Accessibility" in line for line in help_lines)
        assert any("Microphone" in line for line in help_lines)

    def test_global_key_permission_help(self):
        p = MacOSPlatform()
        help_lines = p.get_global_key_permission_help()
        assert len(help_lines) == 2
        assert any("Input Monitoring" in line for line in help_lines)
        assert any("Accessibility" in line for line in help_lines)
        assert not any("Microphone" in line for line in help_lines)

    def test_microphone_permission_help(self):
        p = MacOSPlatform()
        help_lines = p.get_microphone_permission_help()
        assert len(help_lines) == 1
        assert "Microphone" in help_lines[0]

    def test_paste_text_calls_pbcopy(self):
        p = MacOSPlatform()
        with patch("subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.macos.time"), \
             patch("pynput.keyboard.Controller") as mock_ctrl:
            mock_proc = MagicMock()
            mock_popen.return_value = mock_proc
            p.paste_text("hello")
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "pbcopy"

    def test_play_success_sound(self):
        p = MacOSPlatform()
        with patch("subprocess.Popen") as mock_popen:
            p.play_success_sound()
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "afplay"


class TestMacOSParsePttChord:
    def test_single_key(self):
        p = MacOSPlatform()
        result = p.parse_ptt_chord("alt_r")
        key_map = p.get_key_map()
        assert result == frozenset({key_map["alt_r"]})

    def test_multi_key_chord(self):
        p = MacOSPlatform()
        result = p.parse_ptt_chord("ctrl+alt_r")
        key_map = p.get_key_map()
        assert result == frozenset({key_map["ctrl"], key_map["alt_r"]})

    def test_three_key_chord(self):
        p = MacOSPlatform()
        result = p.parse_ptt_chord("ctrl+shift_l+alt_r")
        key_map = p.get_key_map()
        assert result == frozenset({key_map["ctrl"], key_map["shift_l"], key_map["alt_r"]})

    def test_modifier_and_number_chord(self):
        p = MacOSPlatform()
        result = p.parse_ptt_chord("ctrl+1")
        key_map = p.get_key_map()
        assert result == frozenset({key_map["ctrl"], key_map["1"]})

    def test_unknown_key_raises(self):
        p = MacOSPlatform()
        with pytest.raises(PlatformError, match="Unknown key"):
            p.parse_ptt_chord("nonexistent_key")

    def test_unknown_key_in_chord_raises(self):
        p = MacOSPlatform()
        with pytest.raises(PlatformError, match="Unknown key"):
            p.parse_ptt_chord("ctrl+nonexistent")

    def test_empty_parts_ignored(self):
        p = MacOSPlatform()
        key_map = p.get_key_map()
        result = p.parse_ptt_chord("alt_r")
        assert result == frozenset({key_map["alt_r"]})


class TestMacOSChordDisplayName:
    def test_single_key_display(self):
        p = MacOSPlatform()
        result = p.get_chord_display_name("alt_r")
        assert "Option" in result

    def test_chord_display(self):
        p = MacOSPlatform()
        result = p.get_chord_display_name("ctrl+alt_r")
        assert "Control" in result
        assert "Option" in result
        assert "+" in result

    def test_f_key_display(self):
        p = MacOSPlatform()
        result = p.get_chord_display_name("f18")
        assert "F18" in result


class TestMacOSIsModifierOnly:
    def test_single_modifier_is_modifier_only(self):
        p = MacOSPlatform()
        assert p.is_modifier_only("alt_r") is True

    def test_single_f_key_is_not_modifier_only(self):
        p = MacOSPlatform()
        assert p.is_modifier_only("f18") is False

    def test_chord_with_modifier_and_fkey(self):
        p = MacOSPlatform()
        assert p.is_modifier_only("ctrl+f18") is False

    def test_chord_all_modifiers(self):
        p = MacOSPlatform()
        assert p.is_modifier_only("ctrl+alt_r") is True


class TestLinuxPlatform:
    def test_all_methods_raise(self):
        p = LinuxPlatform()
        with pytest.raises(PlatformNotSupportedError):
            p.get_key_map()
        with pytest.raises(PlatformNotSupportedError):
            p.get_key_display_names()
        with pytest.raises(PlatformNotSupportedError):
            p.get_default_ptt_key()
        with pytest.raises(PlatformNotSupportedError):
            p.parse_ptt_chord("alt_r")
        with pytest.raises(PlatformNotSupportedError):
            p.get_chord_display_name("alt_r")
        with pytest.raises(PlatformNotSupportedError):
            p.is_modifier_only("alt_r")
        with pytest.raises(PlatformNotSupportedError):
            p.paste_text("test")
        with pytest.raises(PlatformNotSupportedError):
            p.play_success_sound()
        with pytest.raises(PlatformNotSupportedError):
            p.get_permission_help()


class TestWindowsPlatform:
    def test_all_methods_raise(self):
        p = WindowsPlatform()
        with pytest.raises(PlatformNotSupportedError):
            p.get_key_map()
        with pytest.raises(PlatformNotSupportedError):
            p.get_key_display_names()
        with pytest.raises(PlatformNotSupportedError):
            p.get_default_ptt_key()
        with pytest.raises(PlatformNotSupportedError):
            p.parse_ptt_chord("alt_r")
        with pytest.raises(PlatformNotSupportedError):
            p.get_chord_display_name("alt_r")
        with pytest.raises(PlatformNotSupportedError):
            p.is_modifier_only("alt_r")
        with pytest.raises(PlatformNotSupportedError):
            p.paste_text("test")
        with pytest.raises(PlatformNotSupportedError):
            p.play_success_sound()
        with pytest.raises(PlatformNotSupportedError):
            p.get_permission_help()


class TestPlatformDetect:
    def test_detect_macos(self):
        import sys
        with patch.object(sys, "platform", "darwin"):
            from talk_to_vibe.platforms.detect import get_platform
            p = get_platform()
            assert isinstance(p, MacOSPlatform)

    def test_detect_linux(self):
        import sys
        with patch.object(sys, "platform", "linux"):
            from talk_to_vibe.platforms.detect import get_platform
            p = get_platform()
            assert isinstance(p, LinuxPlatform)

    def test_detect_windows(self):
        import sys
        with patch.object(sys, "platform", "win32"):
            from talk_to_vibe.platforms.detect import get_platform
            p = get_platform()
            assert isinstance(p, WindowsPlatform)

    def test_detect_unsupported(self):
        import sys
        with patch.object(sys, "platform", "freebsd"):
            from talk_to_vibe.platforms.detect import get_platform
            with pytest.raises(PlatformNotSupportedError):
                get_platform()
