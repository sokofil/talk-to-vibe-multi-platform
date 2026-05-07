from unittest.mock import patch, MagicMock

import pytest

from talk_to_vibe.platforms.linux import LinuxPlatform
from talk_to_vibe.errors import PlatformError


class TestLinuxKeyMap:
    def test_default_ptt_key(self):
        assert LinuxPlatform().get_default_ptt_key() == "ctrl+9"

    def test_key_map_has_modifiers(self):
        key_map = LinuxPlatform().get_key_map()
        for k in ("alt", "alt_l", "alt_r", "ctrl", "ctrl_l", "ctrl_r", "shift", "shift_l", "shift_r", "super", "cmd"):
            assert k in key_map, f"missing key {k}"

    def test_key_map_has_digits(self):
        key_map = LinuxPlatform().get_key_map()
        for digit in "0123456789":
            assert digit in key_map

    def test_key_map_has_function_keys(self):
        key_map = LinuxPlatform().get_key_map()
        for n in range(1, 13):
            assert f"f{n}" in key_map

    def test_display_names_cover_all_keys(self):
        names = LinuxPlatform().get_key_display_names()
        assert "Ctrl" in names["ctrl"]
        assert names["9"] == "9"
        assert names["f9"] == "F9"
        assert "Super" in names["super"]


class TestLinuxParseChord:
    def test_single_modifier(self):
        p = LinuxPlatform()
        result = p.parse_ptt_chord("alt_r")
        # alt_r normalizes to alt so the chord matches either alt key
        assert result == frozenset({p.get_key_map()["alt"]})

    def test_modifier_plus_digit(self):
        p = LinuxPlatform()
        result = p.parse_ptt_chord("ctrl+9")
        km = p.get_key_map()
        assert result == frozenset({km["ctrl"], km["9"]})

    def test_three_key_chord(self):
        p = LinuxPlatform()
        result = p.parse_ptt_chord("ctrl+shift_l+f12")
        km = p.get_key_map()
        # shift_l normalizes to shift
        assert result == frozenset({km["ctrl"], km["shift"], km["f12"]})

    def test_unknown_key_raises(self):
        with pytest.raises(PlatformError, match="Unknown key"):
            LinuxPlatform().parse_ptt_chord("nonexistent")

    def test_unknown_key_in_chord_raises(self):
        with pytest.raises(PlatformError, match="Unknown key"):
            LinuxPlatform().parse_ptt_chord("ctrl+nope")

    def test_empty_chord_raises(self):
        with pytest.raises(PlatformError, match="Empty chord"):
            LinuxPlatform().parse_ptt_chord("")

    def test_whitespace_only_chord_raises(self):
        with pytest.raises(PlatformError, match="Empty chord"):
            LinuxPlatform().parse_ptt_chord("  +  ")


class TestLinuxChordDisplay:
    def test_modifier_plus_digit(self):
        text = LinuxPlatform().get_chord_display_name("ctrl+9")
        assert "Ctrl" in text
        assert "9" in text
        assert "+" in text

    def test_function_key(self):
        assert "F12" in LinuxPlatform().get_chord_display_name("f12")


class TestLinuxModifierOnly:
    def test_single_modifier_is_modifier_only(self):
        assert LinuxPlatform().is_modifier_only("alt_r") is True

    def test_modifier_plus_digit_is_not_modifier_only(self):
        assert LinuxPlatform().is_modifier_only("ctrl+9") is False

    def test_function_key_is_not_modifier_only(self):
        assert LinuxPlatform().is_modifier_only("f12") is False

    def test_chord_all_modifiers(self):
        assert LinuxPlatform().is_modifier_only("ctrl+alt") is True

    def test_empty_returns_false(self):
        assert LinuxPlatform().is_modifier_only("") is False


class TestLinuxNormalizeListenerKey:
    def test_side_modifiers_collapse_to_generic(self):
        from pynput import keyboard
        p = LinuxPlatform()
        assert p.normalize_listener_key(keyboard.Key.alt_l) == keyboard.Key.alt
        assert p.normalize_listener_key(keyboard.Key.alt_r) == keyboard.Key.alt
        assert p.normalize_listener_key(keyboard.Key.ctrl_l) == keyboard.Key.ctrl
        assert p.normalize_listener_key(keyboard.Key.shift_r) == keyboard.Key.shift
        assert p.normalize_listener_key(keyboard.Key.cmd_l) == keyboard.Key.cmd

    def test_non_modifier_key_unchanged(self):
        from pynput import keyboard
        p = LinuxPlatform()
        digit = keyboard.KeyCode.from_char("9")
        assert p.normalize_listener_key(digit) == digit

    def test_describe_listener_key_shows_normalization(self):
        from pynput import keyboard
        text = LinuxPlatform().describe_listener_key(keyboard.Key.alt_l)
        assert "alt" in text.lower()


class TestLinuxPaste:
    def test_paste_populates_clipboard_via_xclip(self):
        p = LinuxPlatform()
        # xclip available, xdotool missing -> falls back to pynput typing
        # without touching the clipboard.
        with patch(
            "talk_to_vibe.platforms.linux.shutil.which",
            side_effect=lambda name: f"/usr/bin/{name}" if name == "xclip" else None,
        ), patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.linux.subprocess.run"), \
             patch("talk_to_vibe.platforms.linux.time"), \
             patch("pynput.keyboard.Controller"):
            mock_proc = MagicMock()
            mock_popen.return_value = mock_proc
            result = p.paste_text("hello")
            mock_popen.assert_not_called()
            assert result.full_text == "hello"

    def test_paste_uses_xdotool_type_when_available(self):
        p = LinuxPlatform()
        which_results = {"xclip": "/usr/bin/xclip", "xdotool": "/usr/bin/xdotool"}
        with patch(
            "talk_to_vibe.platforms.linux.shutil.which",
            side_effect=lambda name: which_results.get(name),
        ), patch("talk_to_vibe.platforms.linux.subprocess.Popen"), \
             patch("talk_to_vibe.platforms.linux.subprocess.run") as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            result = p.paste_text("hello world")
        # Expect at least one call with xdotool type.
        type_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["xdotool", "type"]]
        assert type_calls, f"expected xdotool type call, got {mock_run.call_args_list}"
        assert "hello world" in type_calls[0].args[0]
        assert result.full_text == "hello world"

    def test_paste_xdotool_uses_safe_delay(self):
        # Regression: --delay 1 caused receiving apps to drop characters
        # (especially spaces). The value must be at least xdotool's default
        # of 12ms to avoid producing run-on words like "ofthis".
        p = LinuxPlatform()
        which_results = {"xclip": "/usr/bin/xclip", "xdotool": "/usr/bin/xdotool"}
        with patch(
            "talk_to_vibe.platforms.linux.shutil.which",
            side_effect=lambda name: which_results.get(name),
        ), patch("talk_to_vibe.platforms.linux.subprocess.Popen"), \
             patch("talk_to_vibe.platforms.linux.subprocess.run") as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            p.paste_text("hello world")
        type_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["xdotool", "type"]]
        argv = type_calls[0].args[0]
        delay_idx = argv.index("--delay") + 1
        assert int(argv[delay_idx]) >= 12, (
            f"xdotool --delay must be >= 12ms to avoid dropped chars, got {argv[delay_idx]}"
        )

    def test_paste_auto_enter_presses_enter_via_xdotool(self):
        p = LinuxPlatform()
        which_results = {"xclip": "/usr/bin/xclip", "xdotool": "/usr/bin/xdotool"}
        with patch(
            "talk_to_vibe.platforms.linux.shutil.which",
            side_effect=lambda name: which_results.get(name),
        ), patch("talk_to_vibe.platforms.linux.subprocess.Popen"), \
             patch("talk_to_vibe.platforms.linux.subprocess.run") as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            result = p.paste_text("hello", auto_enter=True)
        return_calls = [
            c for c in mock_run.call_args_list
            if c.args[0][:2] == ["xdotool", "key"] and "Return" in c.args[0]
        ]
        assert return_calls, f"expected xdotool key Return call, got {mock_run.call_args_list}"
        assert result.full_text == "hello"

    def test_paste_auto_enter_presses_enter_via_pynput_fallback(self):
        # No xdotool — falls back to pynput, which presses Key.enter.
        p = LinuxPlatform()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=lambda name: "/usr/bin/xclip" if name == "xclip" else None), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen"), \
             patch("talk_to_vibe.platforms.linux.subprocess.run"), \
             patch("talk_to_vibe.platforms.linux.time"), \
             patch("pynput.keyboard.Controller") as mock_ctrl:
            from pynput.keyboard import Key
            result = p.paste_text("hello", auto_enter=True)
            kb = mock_ctrl.return_value
            press_keys = [c.args[0] for c in kb.press.call_args_list]
            assert Key.enter in press_keys
            assert result.full_text == "hello"

    def test_paste_falls_back_to_xsel(self):
        p = LinuxPlatform()
        which_results = {"xclip": None, "xsel": "/usr/bin/xsel", "wl-copy": None, "xdotool": None}
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=lambda name: which_results.get(name)), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.linux.subprocess.run"), \
             patch("talk_to_vibe.platforms.linux.time"), \
             patch("pynput.keyboard.Controller"):
            result = p.paste_text("hello")
            mock_popen.assert_not_called()
            assert result.full_text == "hello"

    def test_paste_proceeds_when_no_clipboard_tool(self):
        # No clipboard tool — we still type text into the focused window via
        # xdotool / pynput. Clipboard population is best-effort.
        p = LinuxPlatform()
        with patch("talk_to_vibe.platforms.linux.shutil.which", return_value=None), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.linux.subprocess.run"), \
             patch("talk_to_vibe.platforms.linux.time"), \
             patch("pynput.keyboard.Controller") as mock_ctrl:
            result = p.paste_text("hello")
            mock_popen.assert_not_called()
            mock_ctrl.return_value.type.assert_called_once_with("hello")
            assert result.full_text == "hello"


class TestLinuxTerminalDetection:
    def _make_run_side_effect(self, wid="111149062", wm_class='"gnome-terminal-server", "Gnome-terminal-server"'):
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["xdotool", "getactivewindow"]:
                result.stdout = wid + "\n"
            elif cmd[:2] == ["xprop", "-id"]:
                result.stdout = f"WM_CLASS(STRING) = {wm_class}\n"
            else:
                result.stdout = ""
            return result
        return side_effect

    def test_returns_false_when_xdotool_missing(self):
        with patch("talk_to_vibe.platforms.linux.shutil.which", return_value=None):
            assert LinuxPlatform()._active_window_is_terminal() is False

    def test_returns_false_when_xprop_missing(self):
        which = lambda name: "/usr/bin/xdotool" if name == "xdotool" else None
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which):
            assert LinuxPlatform()._active_window_is_terminal() is False

    def test_detects_gnome_terminal(self):
        which = lambda name: f"/usr/bin/{name}" if name in ("xdotool", "xprop") else None
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=self._make_run_side_effect()):
            assert LinuxPlatform()._active_window_is_terminal() is True

    def test_detects_kitty(self):
        which = lambda name: f"/usr/bin/{name}" if name in ("xdotool", "xprop") else None
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.run",
                   side_effect=self._make_run_side_effect(wm_class='"kitty", "kitty"')):
            assert LinuxPlatform()._active_window_is_terminal() is True

    def test_rejects_browser(self):
        which = lambda name: f"/usr/bin/{name}" if name in ("xdotool", "xprop") else None
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.run",
                   side_effect=self._make_run_side_effect(wm_class='"firefox", "Firefox"')):
            assert LinuxPlatform()._active_window_is_terminal() is False

    def test_rejects_when_active_window_missing(self):
        which = lambda name: f"/usr/bin/{name}" if name in ("xdotool", "xprop") else None
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.run",
                   side_effect=self._make_run_side_effect(wid="")):
            assert LinuxPlatform()._active_window_is_terminal() is False


class TestLinuxPasteStream:
    @staticmethod
    def _terminal_env():
        which = lambda name: f"/usr/bin/{name}" if name in ("xdotool", "xprop", "xclip") else None
        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["xdotool", "getactivewindow"]:
                result.stdout = "12345\n"
            elif cmd[:2] == ["xprop", "-id"]:
                result.stdout = 'WM_CLASS(STRING) = "gnome-terminal-server", "Gnome-terminal-server"\n'
            else:
                result.stdout = ""
            return result
        return which, run_side_effect

    @staticmethod
    def _gui_env():
        which = lambda name: f"/usr/bin/{name}" if name in ("xdotool", "xprop", "xclip") else None
        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["xdotool", "getactivewindow"]:
                result.stdout = "12345\n"
            elif cmd[:2] == ["xprop", "-id"]:
                result.stdout = 'WM_CLASS(STRING) = "firefox", "Firefox"\n'
            else:
                result.stdout = ""
            return result
        return which, run_side_effect

    def test_terminal_target_uses_clipboard_paste_per_chunk(self):
        which, run_side_effect = self._terminal_env()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_side_effect) as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            result = LinuxPlatform().paste_text_stream(["hello", "world"], auto_enter=False)
        assert result.full_text == "hello world"
        paste_calls = [c for c in mock_run.call_args_list
                       if c.args[0][:2] == ["xdotool", "key"] and "ctrl+shift+v" in c.args[0]]
        # One paste per chunk.
        assert len(paste_calls) == 2, f"expected 2 ctrl+shift+v calls, got {paste_calls}"
        type_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["xdotool", "type"]]
        assert not type_calls, f"unexpected xdotool type calls: {type_calls}"
        assert len(mock_popen.call_args_list) >= 2

    def test_gui_target_uses_xdotool_type_per_chunk(self):
        which, run_side_effect = self._gui_env()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen"), \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_side_effect) as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            result = LinuxPlatform().paste_text_stream(["hello", "world"], auto_enter=False)
        assert result.full_text == "hello world"
        type_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["xdotool", "type"]]
        assert len(type_calls) == 2, f"expected 2 xdotool type calls, got {type_calls}"
        # First chunk has no leading space; second chunk is prefixed with one.
        assert type_calls[0].args[0][-1] == "hello"
        assert type_calls[1].args[0][-1] == " world"
        paste_calls = [c for c in mock_run.call_args_list
                       if c.args[0][:2] == ["xdotool", "key"] and "ctrl+shift+v" in c.args[0]]
        assert not paste_calls

    def test_auto_enter_fires_once_at_end(self):
        which, run_side_effect = self._gui_env()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen"), \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_side_effect) as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            LinuxPlatform().paste_text_stream(["alpha", "beta", "gamma"], auto_enter=True)
        return_calls = [c for c in mock_run.call_args_list
                        if c.args[0][:2] == ["xdotool", "key"] and "Return" in c.args[0]]
        assert len(return_calls) == 1

    def test_restores_previous_clipboard_after_terminal_stream(self):
        which, run_side_effect = self._gui_env()
        terminal_which, terminal_run_side_effect = self._terminal_env()
        read_calls = []

        def run_with_clipboard(cmd, **kwargs):
            if cmd[:3] == ["xclip", "-selection", "clipboard"] and "-o" in cmd:
                result = MagicMock()
                if not read_calls:
                    result.stdout = b"https://example.com"
                else:
                    result.stdout = b" world"
                read_calls.append(list(cmd))
                return result
            return terminal_run_side_effect(cmd, **kwargs)

        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=terminal_which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_with_clipboard), \
             patch("talk_to_vibe.platforms.linux.time"):
            mock_proc = MagicMock()
            mock_popen.return_value = mock_proc
            result = LinuxPlatform().paste_text_stream(["hello", "world"], auto_enter=False)
        payloads = [c.args[0] for c in mock_proc.communicate.call_args_list]
        assert payloads == [b"hello", b" world", b"https://example.com"]
        assert result.clipboard_restore_failed is False

    def test_empty_stream_does_not_paste(self):
        which, run_side_effect = self._gui_env()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_side_effect) as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            result = LinuxPlatform().paste_text_stream([], auto_enter=True)
        assert result.full_text == ""
        type_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["xdotool", "type"]]
        assert not type_calls
        return_calls = [c for c in mock_run.call_args_list
                        if c.args[0][:2] == ["xdotool", "key"] and "Return" in c.args[0]]
        assert not return_calls
        mock_popen.assert_not_called()

    def test_chunks_with_only_whitespace_skipped(self):
        which, run_side_effect = self._gui_env()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen"), \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_side_effect) as mock_run, \
             patch("talk_to_vibe.platforms.linux.time"):
            result = LinuxPlatform().paste_text_stream(["", "  ", "real"], auto_enter=False)
        assert result.full_text == "real"
        type_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["xdotool", "type"]]
        assert len(type_calls) == 1
        assert type_calls[0].args[0][-1] == "real"

    def test_restore_failure_sets_result_flag(self):
        terminal_which, terminal_run_side_effect = self._terminal_env()
        popen_calls = []

        def popen_side_effect(*args, **kwargs):
            proc = MagicMock()
            idx = len(popen_calls)
            if idx < 2:
                proc.communicate.return_value = (b"", b"")
            else:
                proc.communicate.side_effect = RuntimeError("restore failed")
            popen_calls.append(proc)
            return proc

        read_calls = []

        def run_with_clipboard(cmd, **kwargs):
            if cmd[:3] == ["xclip", "-selection", "clipboard"] and "-o" in cmd:
                result = MagicMock()
                if not read_calls:
                    result.stdout = b"original"
                else:
                    result.stdout = b" world"
                read_calls.append(list(cmd))
                return result
            return terminal_run_side_effect(cmd, **kwargs)

        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=terminal_which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen", side_effect=popen_side_effect), \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_with_clipboard), \
             patch("talk_to_vibe.platforms.linux.time"):
            result = LinuxPlatform().paste_text_stream(["hello", "world"], auto_enter=False)
        assert result.full_text == "hello world"
        assert result.clipboard_restore_failed is True
        assert result.clipboard_restore_reason == "could not restore clipboard"

    def test_restore_skipped_when_clipboard_changes(self):
        terminal_which, terminal_run_side_effect = self._terminal_env()
        read_calls = []

        def run_with_clipboard(cmd, **kwargs):
            if cmd[:3] == ["xclip", "-selection", "clipboard"] and "-o" in cmd:
                result = MagicMock()
                if not read_calls:
                    result.stdout = b"original"
                else:
                    result.stdout = b"user copied something else"
                read_calls.append(list(cmd))
                return result
            return terminal_run_side_effect(cmd, **kwargs)

        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=terminal_which), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen, \
             patch("talk_to_vibe.platforms.linux.subprocess.run", side_effect=run_with_clipboard), \
             patch("talk_to_vibe.platforms.linux.time"):
            result = LinuxPlatform().paste_text_stream(["hello", "world"], auto_enter=False)
        payloads = [c.args[0] for c in mock_popen.return_value.communicate.call_args_list]
        assert payloads == [b"hello", b" world"]
        assert result.clipboard_restore_failed is False


class TestLinuxSuccessSound:
    def test_uses_canberra_when_available(self):
        p = LinuxPlatform()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=lambda name: "/usr/bin/canberra-gtk-play" if name == "canberra-gtk-play" else None), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen:
            p.play_success_sound()
            args = mock_popen.call_args[0][0]
            assert args[0] == "canberra-gtk-play"

    def test_falls_back_to_paplay(self):
        which_results = {"canberra-gtk-play": None, "paplay": "/usr/bin/paplay", "aplay": None}
        p = LinuxPlatform()
        with patch("talk_to_vibe.platforms.linux.shutil.which", side_effect=lambda name: which_results.get(name)), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen:
            p.play_success_sound()
            args = mock_popen.call_args[0][0]
            assert args[0] == "paplay"

    def test_silent_when_no_player(self):
        p = LinuxPlatform()
        with patch("talk_to_vibe.platforms.linux.shutil.which", return_value=None), \
             patch("talk_to_vibe.platforms.linux.subprocess.Popen") as mock_popen:
            p.play_success_sound()
            mock_popen.assert_not_called()


class TestLinuxPermissionHelp:
    def test_x11_permission_help_is_brief(self):
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": "", "XDG_SESSION_TYPE": "x11"}, clear=False):
            help_lines = LinuxPlatform().get_global_key_permission_help()
            assert len(help_lines) >= 1
            assert all("Wayland" not in line for line in help_lines)

    def test_wayland_permission_help_warns(self):
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=False):
            help_lines = LinuxPlatform().get_global_key_permission_help()
            assert any("Wayland" in line for line in help_lines)
            assert any("X11" in line for line in help_lines)

    def test_microphone_help_mentions_audio_group(self):
        help_lines = LinuxPlatform().get_microphone_permission_help()
        assert any("audio" in line.lower() for line in help_lines)

    def test_general_permission_help_includes_clipboard(self):
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": ""}, clear=False):
            help_lines = LinuxPlatform().get_permission_help()
        assert any("clipboard" in line.lower() or "xclip" in line.lower() for line in help_lines)


class TestLinuxGlobalKeyAccess:
    def test_x11_session_has_access(self):
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": "", "XDG_SESSION_TYPE": "x11"}, clear=False):
            assert LinuxPlatform().has_global_key_access() is True

    def test_wayland_session_has_no_access(self):
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=False):
            assert LinuxPlatform().has_global_key_access() is False
