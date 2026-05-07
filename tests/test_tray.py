from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

from talk_to_vibe.platforms.base import PasteResult
from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.tray import (
    ICON_IDLE,
    ICON_RECORDING,
    ICON_TRANSCRIBING,
    build_state_icons,
)


class FakeSTT(BaseSTTProvider):
    provider_name = "Fake"
    model = "fake-model-v1"

    def __init__(self, return_text="hello world", should_raise=None):
        self._return_text = return_text
        self._should_raise = should_raise

    def transcribe(self, audio_data):
        if self._should_raise:
            raise self._should_raise
        return self._return_text


class FakeKey:
    def __init__(self, name: str):
        self._name = name

    def __eq__(self, other):
        return isinstance(other, FakeKey) and self._name == other._name

    def __hash__(self):
        return hash(self._name)

    def __repr__(self):
        return f"FakeKey({self._name!r})"


FAKE_ALT_R = FakeKey("alt_r")
FAKE_ALT = FakeKey("alt")
FAKE_CTRL = FakeKey("ctrl")


def _mock_platform():
    mock_platform = MagicMock()
    mock_platform.get_key_map.return_value = {
        "alt_r": FAKE_ALT, "alt_l": FAKE_ALT, "alt": FAKE_ALT, "ctrl": FAKE_CTRL,
    }
    mock_platform.get_default_ptt_key.return_value = "alt_r"
    mock_platform.has_global_key_access.return_value = True
    mock_platform.normalize_listener_key.side_effect = lambda key: FAKE_ALT if key == FAKE_ALT_R else key
    mock_platform.describe_listener_key.side_effect = lambda key: repr(key)
    mock_platform.build_listener_kwargs.return_value = {}
    mock_platform.get_global_key_permission_help.return_value = ["X11 session: no extra permissions required."]
    mock_platform.parse_ptt_chord.side_effect = lambda s: frozenset(
        {FAKE_ALT} if s in {"alt_r", "alt_l", "alt"} else
        {FAKE_CTRL, FAKE_ALT} if s == "ctrl+alt_r" else set()
    )
    mock_platform.get_chord_display_name.side_effect = lambda s: s.replace("+", " + ")
    mock_platform.paste_text.return_value = PasteResult(full_text="hello world")
    return mock_platform


def _make_tray(stt=None, **kwargs):
    with patch("talk_to_vibe.tray.get_platform", return_value=_mock_platform()):
        from talk_to_vibe.tray import TalkToVibeTray
        stt = stt or FakeSTT()
        return TalkToVibeTray(stt=stt, ptt_key_name=kwargs.pop("ptt_key_name", "alt_r"), **kwargs)


class TestBuildStateIcons:
    def test_returns_three_states(self):
        icons = build_state_icons()
        assert set(icons.keys()) == {ICON_IDLE, ICON_RECORDING, ICON_TRANSCRIBING}

    def test_icons_are_pil_images(self):
        from PIL import Image
        for img in build_state_icons().values():
            assert isinstance(img, Image.Image)
            assert img.size == (64, 64)


class TestTrayInit:
    def test_chord_parsed_at_init(self):
        tray = _make_tray(ptt_key_name="alt_r")
        assert tray.ptt_chord == frozenset({FAKE_ALT})

    def test_multi_key_chord(self):
        tray = _make_tray(ptt_key_name="ctrl+alt_r")
        assert tray.ptt_chord == frozenset({FAKE_CTRL, FAKE_ALT})

    def test_held_keys_initially_empty(self):
        assert _make_tray().held_keys == set()

    def test_state_icons_loaded(self):
        tray = _make_tray()
        assert ICON_IDLE in tray._icons
        assert ICON_RECORDING in tray._icons
        assert ICON_TRANSCRIBING in tray._icons

    def test_initial_state_is_idle(self):
        tray = _make_tray()
        assert tray._current_state == ICON_IDLE

    def test_prompt_file_stored(self):
        tray = _make_tray(prompt_file="~/my_prompt.md")
        assert tray.prompt_file == "~/my_prompt.md"


class TestTrayChordPress:
    def test_press_starts_recording(self):
        tray = _make_tray()
        with patch.object(tray, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            tray.on_key_press(FAKE_ALT_R)
        assert tray.is_recording is True
        assert tray._chord_armed is True
        assert tray._current_state == ICON_RECORDING

    def test_partial_chord_does_not_toggle(self):
        tray = _make_tray(ptt_key_name="ctrl+alt_r")
        with patch.object(tray, "recorder") as mock_rec:
            tray.on_key_press(FAKE_CTRL)
        mock_rec.start.assert_not_called()
        assert tray.is_recording is False

    def test_repeat_press_while_armed_is_ignored(self):
        tray = _make_tray()
        with patch.object(tray, "_start_recording") as mock_start, patch.object(tray, "_stop_recording") as mock_stop:
            tray.on_key_press(FAKE_ALT_R)
            tray.on_key_press(FAKE_ALT_R)
        mock_start.assert_called_once()
        mock_stop.assert_not_called()

    def test_press_ignored_during_paste(self):
        tray = _make_tray()
        tray._paste_in_progress = True
        tray.on_key_press(FAKE_ALT_R)
        assert FAKE_ALT not in tray.held_keys

    def test_press_ignored_while_processing(self):
        tray = _make_tray()
        tray.processing = True
        with patch.object(tray, "_start_recording") as mock_start:
            tray.on_key_press(FAKE_ALT_R)
        mock_start.assert_not_called()


class TestTrayChordRelease:
    def test_release_removes_from_held_keys(self):
        tray = _make_tray()
        with patch.object(tray, "_start_recording"):
            tray.on_key_press(FAKE_ALT_R)
        assert FAKE_ALT in tray.held_keys
        tray.on_key_release(FAKE_ALT_R)
        assert FAKE_ALT not in tray.held_keys

    def test_release_disarms_chord(self):
        tray = _make_tray()
        tray.held_keys.add(FAKE_ALT)
        tray._chord_armed = True
        tray.on_key_release(FAKE_ALT_R)
        assert tray._chord_armed is False

    def test_release_ignored_during_paste(self):
        tray = _make_tray()
        tray._paste_in_progress = True
        tray.held_keys.add(FAKE_ALT_R)
        tray.on_key_release(FAKE_ALT_R)
        assert FAKE_ALT_R in tray.held_keys


class TestTrayToggle:
    def test_second_press_stops_recording(self):
        tray = _make_tray()
        with patch.object(tray, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            tray.on_key_press(FAKE_ALT_R)
            tray.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (np.zeros((16000, 1), dtype=np.int16), 1.0)
            with patch("talk_to_vibe.tray.threading.Thread") as mock_thread:
                thread = MagicMock()
                mock_thread.return_value = thread
                tray.on_key_press(FAKE_ALT_R)
        assert tray.is_recording is False
        assert tray.processing is True
        assert tray._current_state == ICON_TRANSCRIBING
        thread.start.assert_called_once()

    def test_short_recording_stays_idle(self):
        tray = _make_tray()
        with patch.object(tray, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            tray.on_key_press(FAKE_ALT_R)
            tray.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (None, 0.0)
            with patch("talk_to_vibe.tray.threading.Thread") as mock_thread:
                tray.on_key_press(FAKE_ALT_R)
        assert tray.processing is False
        assert tray._current_state == ICON_IDLE
        mock_thread.assert_not_called()

    def test_start_failure_resets_state_to_idle(self):
        tray = _make_tray()
        with patch.object(tray, "recorder") as mock_rec:
            mock_rec.start.return_value = False
            tray.on_key_press(FAKE_ALT_R)
        assert tray.is_recording is False
        assert tray._current_state == ICON_IDLE


class TestTrayProcess:
    def test_successful_transcription_pastes_and_returns_idle(self):
        tray = _make_tray(stt=FakeSTT(return_text="hello"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch.object(tray, "_notify"):
            tray._process(audio, 1.0)
        assert tray.processing is False
        assert tray._current_state == ICON_IDLE
        tray.platform.paste_text.assert_called_once_with("hello", auto_enter=False)
        tray.platform.play_success_sound.assert_called_once()

    def test_empty_transcription_notifies_empty(self):
        tray = _make_tray(stt=FakeSTT(return_text=""))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch.object(tray, "_notify") as mock_notify:
            tray._process(audio, 1.0)
        # Empty stays as a notification so users know dictation didn't capture.
        assert any("Empty" in c.args[0] for c in mock_notify.call_args_list)
        tray.platform.paste_text.assert_not_called()

    def test_successful_transcription_does_not_notify(self):
        # Successful dictations don't notify — the pasted text is the feedback.
        tray = _make_tray(stt=FakeSTT(return_text="hello"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch.object(tray, "_notify") as mock_notify:
            tray._process(audio, 1.0)
        mock_notify.assert_not_called()

    def test_clipboard_restore_failure_notifies(self):
        tray = _make_tray(stt=FakeSTT(return_text="hello"))
        tray.platform.paste_text.return_value = PasteResult(
            full_text="hello",
            clipboard_restore_failed=True,
            clipboard_restore_reason="could not restore clipboard",
        )
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch.object(tray, "_notify") as mock_notify:
            tray._process(audio, 1.0)
        assert any("Clipboard" in c.args[0] for c in mock_notify.call_args_list)

    def test_error_transcription(self):
        tray = _make_tray(stt=FakeSTT(should_raise=RuntimeError("API down")))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch.object(tray, "_notify") as mock_notify:
            tray._process(audio, 1.0)
        assert tray._current_state == ICON_IDLE
        assert tray.processing is False
        assert any("Error" in c.args[0] for c in mock_notify.call_args_list)

    def test_paste_flag_cleared_after_process(self):
        tray = _make_tray(stt=FakeSTT(return_text="hello"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch.object(tray, "_notify"):
            tray._process(audio, 1.0)
        assert tray._paste_in_progress is False

    def test_paste_flag_cleared_on_error(self):
        tray = _make_tray(stt=FakeSTT(should_raise=RuntimeError("fail")))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch.object(tray, "_notify"):
            tray._process(audio, 1.0)
        assert tray._paste_in_progress is False


class TestTrayNotify:
    def test_notify_send_invoked_when_available(self):
        tray = _make_tray()
        with patch("talk_to_vibe.tray.shutil.which", return_value="/usr/bin/notify-send"), \
             patch("talk_to_vibe.tray.subprocess.Popen") as mock_popen:
            tray._notify("Sub", "Body")
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "notify-send"
            assert any("Sub" in a for a in args)

    def test_notify_silent_when_notify_send_missing(self):
        tray = _make_tray()
        with patch("talk_to_vibe.tray.shutil.which", return_value=None), \
             patch("talk_to_vibe.tray.subprocess.Popen") as mock_popen:
            tray._notify("Sub", "Body")
            mock_popen.assert_not_called()


class TestTrayAutoEnterToggle:
    def test_toggle_flips_value(self):
        tray = _make_tray(auto_enter=False)
        with patch("talk_to_vibe.tray.load_config") as mock_load, \
             patch("talk_to_vibe.tray.save_config"), \
             patch.object(tray, "_notify"):
            mock_load.return_value = MagicMock(auto_enter=False)
            tray._toggle_auto_enter()
        assert tray.auto_enter is True

    def test_toggle_saves_config(self):
        tray = _make_tray(auto_enter=False)
        with patch("talk_to_vibe.tray.load_config") as mock_load, \
             patch("talk_to_vibe.tray.save_config") as mock_save, \
             patch.object(tray, "_notify"):
            mock_load.return_value = MagicMock(auto_enter=False)
            tray._toggle_auto_enter()
            mock_save.assert_called_once()


class TestTrayReconfigure:
    def test_reconfigure_uses_first_available_terminal(self):
        tray = _make_tray()
        with patch("talk_to_vibe.tray.shutil.which", side_effect=lambda name: "/usr/bin/gnome-terminal" if name == "gnome-terminal" else None), \
             patch("talk_to_vibe.tray.subprocess.Popen") as mock_popen, \
             patch.object(tray, "_notify"), \
             patch("pathlib.Path.exists", return_value=True):
            tray._reconfigure()
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "gnome-terminal"

    def test_reconfigure_notifies_when_no_terminal_found(self):
        tray = _make_tray()
        with patch("talk_to_vibe.tray.shutil.which", return_value=None), \
             patch("talk_to_vibe.tray.subprocess.Popen") as mock_popen, \
             patch.object(tray, "_notify") as mock_notify, \
             patch("pathlib.Path.exists", return_value=True):
            tray._reconfigure()
            mock_popen.assert_not_called()
            assert any("terminal" in c.args[1].lower() for c in mock_notify.call_args_list)

    def test_reconfigure_notifies_when_run_script_missing(self):
        tray = _make_tray()
        with patch("pathlib.Path.exists", return_value=False), \
             patch.object(tray, "_notify") as mock_notify, \
             patch("talk_to_vibe.tray.subprocess.Popen") as mock_popen:
            tray._reconfigure()
            mock_popen.assert_not_called()
            mock_notify.assert_called()

    def test_build_terminal_command_uses_candidate_arg_template(self):
        tray = _make_tray()
        with patch("talk_to_vibe.tray.shutil.which", side_effect=lambda name: "/usr/bin/xfce4-terminal" if name == "xfce4-terminal" else None):
            command = tray._build_terminal_command("echo hi")
        assert command == ["xfce4-terminal", "-x", "bash", "-lc", "echo hi"]


class TestTrayCleanup:
    def test_cleanup_stops_recording(self):
        tray = _make_tray()
        tray.is_recording = True
        with patch.object(tray, "recorder") as mock_rec:
            mock_rec.stop.return_value = (None, 0.0)
            tray._cleanup()
        assert tray.is_recording is False

    def test_cleanup_clears_held_keys(self):
        tray = _make_tray()
        tray.held_keys.update({FAKE_ALT_R, FAKE_CTRL})
        tray._cleanup()
        assert tray.held_keys == set()

    def test_quit_calls_cleanup_and_stops_tray(self):
        tray = _make_tray()
        tray._tray = MagicMock()
        with patch.object(tray, "_cleanup") as mock_cleanup:
            tray._quit()
        mock_cleanup.assert_called_once()
        tray._tray.stop.assert_called_once()


class TestTrayListener:
    def test_start_listener_logs_ptt_key(self, caplog):
        tray = _make_tray(ptt_key_name="alt_r")
        caplog.set_level("INFO")
        with patch("pynput.keyboard.Listener") as mock_listener:
            mock_listener.return_value = MagicMock()
            tray._start_listener()
        assert "ptt_key=alt_r" in caplog.text

    def test_start_listener_warns_on_wayland(self):
        tray = _make_tray()
        tray.platform.has_global_key_access.return_value = False
        with patch("pynput.keyboard.Listener") as mock_listener, \
             patch.object(tray, "_notify") as mock_notify:
            mock_listener.return_value = MagicMock()
            tray._start_listener()
        mock_notify.assert_called()
        assert any("Wayland" in c.args[1] or "X11" in c.args[1] for c in mock_notify.call_args_list)

    def test_start_listener_notifies_on_exception(self):
        tray = _make_tray()
        with patch("pynput.keyboard.Listener", side_effect=RuntimeError("listener failed")), \
             patch.object(tray, "_notify") as mock_notify:
            tray._start_listener()
        assert any("listener failed" in c.args[1] for c in mock_notify.call_args_list)
