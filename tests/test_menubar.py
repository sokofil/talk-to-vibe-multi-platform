import signal
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

import rumps as _rumps

from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.menubar import TITLE_IDLE, TITLE_RECORDING, TITLE_TRANSCRIBING


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


def _fake_rumps_init(self, *a, **kw):
    self._name = a[0] if a else "TalkToVibe"
    self._icon = self._icon_nsimage = self._title = None
    self._template = None
    self._quit_button = kw.get("quit_button", "Quit")
    self._application_support = ""
    self._menu = MagicMock()
    title = kw.get("title", self._name)
    if title is not None:
        self.title = title
    else:
        self._title = None


def _mock_platform():
    mock_platform = MagicMock()
    mock_platform.get_key_map.return_value = {"alt_r": FAKE_ALT, "alt_l": FAKE_ALT, "alt": FAKE_ALT, "ctrl": FAKE_CTRL}
    mock_platform.get_default_ptt_key.return_value = "alt_r"
    mock_platform.has_global_key_access.return_value = True
    mock_platform.request_global_key_access.return_value = True
    mock_platform.normalize_listener_key.side_effect = lambda key: FAKE_ALT if key == FAKE_ALT_R else key
    mock_platform.describe_listener_key.side_effect = lambda key: repr(key)
    mock_platform.build_listener_kwargs.return_value = {}
    mock_platform.get_permission_help.return_value = [
        "Input Monitoring: System Settings -> Privacy & Security -> Input Monitoring",
        "Accessibility: System Settings -> Privacy & Security -> Accessibility",
        "Microphone: System Settings -> Privacy & Security -> Microphone",
    ]
    mock_platform.get_global_key_permission_help.return_value = [
        "Input Monitoring: System Settings -> Privacy & Security -> Input Monitoring",
        "Accessibility: System Settings -> Privacy & Security -> Accessibility",
    ]
    mock_platform.get_microphone_permission_help.return_value = [
        "Microphone: System Settings -> Privacy & Security -> Microphone",
    ]
    mock_platform.parse_ptt_chord.side_effect = lambda s: frozenset(
        {FAKE_ALT} if s in {"alt_r", "alt_l", "alt"} else
        {FAKE_CTRL, FAKE_ALT} if s == "ctrl+alt_r" else set()
    )
    mock_platform.get_chord_display_name.side_effect = lambda s: s.replace("+", " + ")
    return mock_platform


def _make_menubar_app(stt=None, **kwargs):
    with patch("talk_to_vibe.menubar.get_platform", return_value=_mock_platform()), \
         patch.object(_rumps.App, "__init__", _fake_rumps_init), \
         patch.object(_rumps.Timer, "start"):
        from talk_to_vibe.menubar import TalkToVibeMenuBar
        stt = stt or FakeSTT()
        app = TalkToVibeMenuBar(stt=stt, ptt_key_name=kwargs.pop("ptt_key_name", "alt_r"), **kwargs)
    return app


class TestMenuBarChordInit:
    def test_single_key_chord(self):
        app = _make_menubar_app(ptt_key_name="alt_r")
        assert app.ptt_chord == frozenset({FAKE_ALT})

    def test_multi_key_chord(self):
        app = _make_menubar_app(ptt_key_name="ctrl+alt_r")
        assert app.ptt_chord == frozenset({FAKE_CTRL, FAKE_ALT})

    def test_held_keys_initially_empty(self):
        app = _make_menubar_app()
        assert len(app.held_keys) == 0

    def test_paste_in_progress_initially_false(self):
        app = _make_menubar_app()
        assert app._paste_in_progress is False

    def test_prompt_file_stored(self):
        app = _make_menubar_app(prompt_file="~/my_prompt.md")
        assert app.prompt_file == "~/my_prompt.md"


class TestMenuBarPermissions:
    def test_start_listener_warns_but_starts_without_global_key_access(self):
        app = _make_menubar_app()
        app.platform.get_global_key_access_status.return_value = {
            "accessibility": False,
            "listen_event": False,
        }
        with patch("talk_to_vibe.menubar.rumps") as mock_rumps, \
             patch("pynput.keyboard.Listener") as mock_listener:
            listener = MagicMock()
            listener._thread = MagicMock()
            mock_listener.return_value = listener
            app._start_listener()
        app.platform.request_global_key_access.assert_called_once()
        notification_message = mock_rumps.notification.call_args[0][2]
        assert "Input Monitoring" in notification_message or "Accessibility" in notification_message
        mock_rumps.alert.assert_not_called()
        mock_listener.assert_called_once()

    def test_start_listener_logs_ptt_key(self, caplog):
        app = _make_menubar_app(ptt_key_name="alt_r")
        caplog.set_level("INFO")
        with patch("pynput.keyboard.Listener") as mock_listener:
            listener = MagicMock()
            mock_listener.return_value = listener
            app._start_listener()
        assert "ptt_key=alt_r" in caplog.text
        listener.start.assert_called_once()

    def test_start_listener_passes_debug_flag_to_platform(self):
        app = _make_menubar_app(ptt_key_name="alt_r")
        app.debug_key_events = True
        with patch("pynput.keyboard.Listener") as mock_listener:
            listener = MagicMock()
            mock_listener.return_value = listener
            app._start_listener()
        app.platform.build_listener_kwargs.assert_called_once_with(app.logger, True)

    def test_start_listener_alerts_on_listener_exception(self):
        app = _make_menubar_app(ptt_key_name="alt_r")
        with patch("pynput.keyboard.Listener", side_effect=RuntimeError("listener failed")), \
             patch("talk_to_vibe.menubar.rumps") as mock_rumps:
            app._start_listener()
        alert_message = mock_rumps.alert.call_args[0][1]
        assert "listener failed" in alert_message


class TestMenuBarChordPress:
    def test_press_starts_recording_immediately(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
        assert app.is_recording is True
        assert app._chord_armed is True

    def test_extra_key_prevents_toggle_for_multi_key_chord(self):
        app = _make_menubar_app(ptt_key_name="ctrl+alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_CTRL)
            app.on_key_press(FakeKey("extra"))
            app.on_key_press(FAKE_ALT_R)
        mock_rec.start.assert_not_called()
        assert app.is_recording is False

    def test_partial_chord_does_not_toggle(self):
        app = _make_menubar_app(ptt_key_name="ctrl+alt_r")
        with patch.object(app, "recorder") as mock_rec:
            app.on_key_press(FAKE_CTRL)
        mock_rec.start.assert_not_called()
        assert app.is_recording is False

    def test_repeat_press_while_armed_is_ignored(self):
        app = _make_menubar_app()
        with patch.object(app, "_start_recording") as mock_start, patch.object(app, "_stop_recording") as mock_stop:
            app.on_key_press(FAKE_ALT_R)
            app.on_key_press(FAKE_ALT_R)
        mock_start.assert_called_once()
        mock_stop.assert_not_called()

    def test_stale_armed_state_is_cleared_before_repeated_press(self):
        app = _make_menubar_app()
        app.held_keys = {FAKE_ALT}
        app._chord_armed = True
        app._last_key_event_at = 1.0
        app._last_chord_arm_at = 1.0
        with patch.object(app, "recorder") as mock_rec, \
             patch("talk_to_vibe.menubar.time.monotonic", return_value=4.5):
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
        mock_rec.start.assert_called_once()
        assert app.is_recording is True

    def test_stale_key_state_is_cleared_before_new_partial_chord(self):
        app = _make_menubar_app(ptt_key_name="ctrl+alt_r")
        app.held_keys = {FAKE_CTRL, FAKE_ALT}
        app._chord_armed = True
        app._last_key_event_at = 1.0
        app._last_chord_arm_at = 1.0
        with patch.object(app, "recorder") as mock_rec, \
             patch("talk_to_vibe.menubar.time.monotonic", return_value=4.5):
            app.on_key_press(FAKE_CTRL)
        mock_rec.start.assert_not_called()
        assert app._chord_armed is False
        assert app.held_keys == {FAKE_CTRL}


class TestMenuBarChordRelease:
    def test_release_removes_from_held_keys(self):
        app = _make_menubar_app()
        with patch.object(app, "_start_recording"):
            app.on_key_press(FAKE_ALT_R)
        assert FAKE_ALT in app.held_keys
        app.on_key_release(FAKE_ALT_R)
        assert FAKE_ALT not in app.held_keys

    def test_release_disarms_chord(self):
        app = _make_menubar_app()
        app.held_keys.add(FAKE_ALT)
        app._chord_armed = True
        app.on_key_release(FAKE_ALT_R)
        assert app._chord_armed is False

    def test_release_non_chord_key_keeps_chord_armed(self):
        app = _make_menubar_app()
        app.held_keys.update({FAKE_ALT, FakeKey("other")})
        app._chord_armed = True
        app.on_key_release(FakeKey("other"))
        assert app._chord_armed is True


class TestMenuBarToggleRecording:
    def test_second_press_stops_recording_after_release(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            app.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (np.zeros((16000, 1), dtype=np.int16), 1.0)
            with patch("talk_to_vibe.menubar.threading.Thread") as mock_thread:
                thread = MagicMock()
                mock_thread.return_value = thread
                app.on_key_press(FAKE_ALT_R)
        assert app.is_recording is False
        assert app.processing is True
        assert app._pending_title == TITLE_TRANSCRIBING
        thread.start.assert_called_once()

    def test_second_press_with_short_recording_is_ignored(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            app.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (None, 0.0)
            with patch("talk_to_vibe.menubar.threading.Thread") as mock_thread:
                app.on_key_press(FAKE_ALT_R)
        assert app.processing is False
        assert app._pending_title == TITLE_IDLE
        mock_thread.assert_not_called()

    def test_press_ignored_while_processing(self):
        app = _make_menubar_app()
        app.processing = True
        with patch.object(app, "_start_recording") as mock_start:
            app.on_key_press(FAKE_ALT_R)
        mock_start.assert_not_called()

    def test_start_failure_resets_idle_title(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = False
            app.on_key_press(FAKE_ALT_R)
        assert app.is_recording is False
        assert app._pending_title == TITLE_IDLE

    def test_start_failure_does_not_log_recording_started(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec, \
             patch.object(app.logger, "info") as mock_info:
            mock_rec.start.return_value = False
            app.on_key_press(FAKE_ALT_R)
        mock_info.assert_not_called()


class TestMenuBarProcess:
    def test_successful_transcription(self):
        app = _make_menubar_app(stt=FakeSTT(return_text="hello world"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert app.processing is False
        assert app._pending_title == TITLE_IDLE

    def test_empty_transcription(self):
        app = _make_menubar_app(stt=FakeSTT(return_text=""))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert app._pending_title == TITLE_IDLE

    def test_error_transcription(self):
        app = _make_menubar_app(stt=FakeSTT(should_raise=RuntimeError("API down")))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert app._pending_title == TITLE_IDLE

    def test_title_scheduled_after_process(self):
        app = _make_menubar_app(stt=FakeSTT(return_text="test"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert app._pending_title == TITLE_IDLE

    def test_processing_flag_reset_on_error(self):
        app = _make_menubar_app(stt=FakeSTT(should_raise=RuntimeError("boom")))
        audio = np.zeros((16000, 1), dtype=np.int16)
        app.processing = True
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert app.processing is False


class TestSetTitle:
    def test_set_title_queues_pending(self):
        from talk_to_vibe.menubar import TITLE_RECORDING
        app = _make_menubar_app()
        app._set_title(TITLE_RECORDING)
        assert app._pending_title == TITLE_RECORDING

    def test_apply_pending_title_sets_title(self):
        from talk_to_vibe.menubar import TITLE_RECORDING
        app = _make_menubar_app()
        app._set_title(TITLE_RECORDING)
        app._apply_pending_title(None)
        assert app.title == TITLE_RECORDING
        assert app._pending_title is None

    def test_apply_pending_title_noop_when_none(self):
        app = _make_menubar_app()
        app._pending_title = None
        app._apply_pending_title(None)
        assert app.title == "🎤"

    def test_title_timer_started(self):
        app = _make_menubar_app()
        assert app._title_timer is not None


class TestPasteInProgress:
    def test_paste_flag_set_during_process(self):
        app = _make_menubar_app(stt=FakeSTT(return_text="hello"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        flag_states = []

        def capture_paste_flag(*a, **kw):
            flag_states.append(app._paste_in_progress)

        app.platform.paste_text = capture_paste_flag
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert any(f is True for f in flag_states)

    def test_paste_flag_cleared_after_process(self):
        app = _make_menubar_app(stt=FakeSTT(return_text="hello"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert app._paste_in_progress is False

    def test_paste_flag_cleared_on_error(self):
        app = _make_menubar_app(stt=FakeSTT(should_raise=RuntimeError("fail")))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        assert app._paste_in_progress is False

    def test_process_inserts_text_via_platform(self):
        app = _make_menubar_app(stt=FakeSTT(return_text="hello"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        with patch("talk_to_vibe.menubar.rumps"):
            app._process(audio, 1.0)
        app.platform.paste_text.assert_called_once_with("hello", auto_enter=False)

    def test_key_press_ignored_during_paste(self):
        app = _make_menubar_app()
        app._paste_in_progress = True
        app.on_key_press(FAKE_ALT_R)
        assert FAKE_ALT_R not in app.held_keys

    def test_key_release_ignored_during_paste(self):
        app = _make_menubar_app()
        app._paste_in_progress = True
        app.held_keys.add(FAKE_ALT_R)
        app.on_key_release(FAKE_ALT_R)
        assert FAKE_ALT_R in app.held_keys


class TestUiQueue:
    def test_notify_queues_from_worker_thread(self):
        app = _make_menubar_app()
        fake_thread = object()
        with patch("talk_to_vibe.menubar.threading.current_thread", return_value=fake_thread), \
             patch("talk_to_vibe.menubar.threading.main_thread", return_value=object()):
            app._notify("Sub", "Body")
        assert app._ui_actions == [("notify", ("Sub", "Body"))]

    def test_alert_queues_from_worker_thread(self):
        app = _make_menubar_app()
        fake_thread = object()
        with patch("talk_to_vibe.menubar.threading.current_thread", return_value=fake_thread), \
             patch("talk_to_vibe.menubar.threading.main_thread", return_value=object()):
            app._alert("Title", "Body")
        assert app._ui_actions == [("alert", ("Title", "Body"))]

    def test_apply_pending_title_flushes_ui_actions(self):
        app = _make_menubar_app()
        app._ui_actions = [("notify", ("Sub", "Body")), ("alert", ("Title", "Body"))]
        with patch("talk_to_vibe.menubar.rumps") as mock_rumps:
            app._apply_pending_title(None)
        mock_rumps.notification.assert_called_once_with("TalkToVibe", "Sub", "Body")
        mock_rumps.alert.assert_called_once_with("Title", "Body")
        assert app._ui_actions == []


class TestMenuBarAutoEnterToggle:
    def test_toggle_flips_value(self):
        app = _make_menubar_app(auto_enter=False)
        assert app.auto_enter is False
        with patch("talk_to_vibe.menubar.load_config") as mock_load, \
             patch("talk_to_vibe.menubar.save_config"):
            mock_load.return_value = MagicMock(auto_enter=False)
            app._toggle_auto_enter(None)
        assert app.auto_enter is True

    def test_toggle_saves_config(self):
        app = _make_menubar_app(auto_enter=False)
        with patch("talk_to_vibe.menubar.load_config") as mock_load, \
             patch("talk_to_vibe.menubar.save_config") as mock_save:
            mock_load.return_value = MagicMock(auto_enter=False)
            app._toggle_auto_enter(None)
            mock_save.assert_called_once()


class TestMenuBarReconfigure:
    def test_reconfigure_prefers_installed_helper(self):
        app = _make_menubar_app()
        with patch("talk_to_vibe.menubar.INSTALLED_CONFIGURE_HELPER_PATH", Path("/tmp/talktovibe-configure")), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("talk_to_vibe.menubar.subprocess") as mock_subprocess, \
             patch("talk_to_vibe.menubar.rumps"):
            app._reconfigure(None)
            call_args = mock_subprocess.Popen.call_args[0][0]
            assert "/tmp/talktovibe-configure" in call_args

    def test_reconfigure_opens_terminal(self):
        app = _make_menubar_app()
        with patch("talk_to_vibe.menubar.subprocess") as mock_subprocess, \
             patch("talk_to_vibe.menubar.rumps"):
            app._reconfigure(None)
            mock_subprocess.Popen.assert_called_once()
            call_args = mock_subprocess.Popen.call_args[0][0]
            assert call_args[0] == "open"
            assert call_args[1] == "-a"
            assert call_args[2] == "Terminal"

    def test_reconfigure_falls_back_to_repo_helper(self):
        app = _make_menubar_app()
        helper_path = Path("/tmp/helper")
        with patch("talk_to_vibe.menubar.INSTALLED_CONFIGURE_HELPER_PATH", helper_path), \
             patch("talk_to_vibe.menubar.Path.exists", side_effect=[False, True]), \
             patch("talk_to_vibe.menubar.subprocess") as mock_subprocess, \
             patch("talk_to_vibe.menubar.rumps"):
            app._reconfigure(None)
            call_args = mock_subprocess.Popen.call_args[0][0]
            assert str(call_args[3]).endswith("run_ttv.sh")

    def test_reconfigure_alerts_when_no_helper_exists(self):
        app = _make_menubar_app()
        with patch("talk_to_vibe.menubar.INSTALLED_CONFIGURE_HELPER_PATH", Path("/tmp/helper")), \
             patch("talk_to_vibe.menubar.Path.exists", return_value=False), \
             patch("talk_to_vibe.menubar.subprocess") as mock_subprocess, \
             patch("talk_to_vibe.menubar.rumps") as mock_rumps:
            app._reconfigure(None)
            mock_subprocess.Popen.assert_not_called()
            mock_rumps.alert.assert_called_once()

    def test_reconfigure_shows_alert(self):
        app = _make_menubar_app()
        with patch("talk_to_vibe.menubar.subprocess"), \
             patch("talk_to_vibe.menubar.rumps") as mock_rumps:
            app._reconfigure(None)
            mock_rumps.alert.assert_called_once()


class TestMenuBarCleanup:
    def test_cleanup_stops_recording(self):
        app = _make_menubar_app()
        app.is_recording = True
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.stop.return_value = (None, 0.0)
            app._cleanup()
        assert app.is_recording is False

    def test_cleanup_disarms_chord(self):
        app = _make_menubar_app()
        app._chord_armed = True
        app._cleanup()
        assert app._chord_armed is False

    def test_cleanup_clears_held_keys(self):
        app = _make_menubar_app()
        app.held_keys.add(FAKE_ALT_R)
        app.held_keys.add(FAKE_CTRL)
        app._cleanup()
        assert len(app.held_keys) == 0

    def test_cleanup_noop_when_idle(self):
        app = _make_menubar_app()
        app._cleanup()
        assert app.is_recording is False
        assert app._chord_armed is False


class TestMenuBarQuit:
    def test_quit_calls_cleanup(self):
        app = _make_menubar_app()
        with patch.object(app, "_cleanup") as mock_cleanup, \
             patch("talk_to_vibe.menubar.rumps.quit_application"):
            app._quit(None)
            mock_cleanup.assert_called_once()

    def test_quit_calls_rumps_quit(self):
        app = _make_menubar_app()
        with patch.object(app, "_cleanup"), \
             patch("talk_to_vibe.menubar.rumps.quit_application") as mock_quit:
            app._quit(None)
            mock_quit.assert_called_once()


class TestMenuBarSigInt:
    def test_sigint_calls_cleanup(self):
        app = _make_menubar_app()
        with patch.object(app, "_cleanup") as mock_cleanup, \
             patch("talk_to_vibe.menubar.rumps.quit_application"):
            app._handle_sigint(signal.SIGINT, None)
            mock_cleanup.assert_called_once()

    def test_sigint_calls_quit(self):
        app = _make_menubar_app()
        with patch.object(app, "_cleanup"), \
             patch("talk_to_vibe.menubar.rumps.quit_application") as mock_quit:
            app._handle_sigint(signal.SIGINT, None)
            mock_quit.assert_called_once()


class TestMenuBarTitleStates:
    def test_idle_title(self):
        app = _make_menubar_app()
        assert app.title == TITLE_IDLE

    def test_recording_queues_title(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
        assert app._pending_title == TITLE_RECORDING

    def test_transcribing_queues_title(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            app.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (np.zeros((16000, 1), dtype=np.int16), 1.0)
            with patch("talk_to_vibe.menubar.threading.Thread"):
                app.on_key_press(FAKE_ALT_R)
        assert app._pending_title == TITLE_TRANSCRIBING

    def test_short_recording_queues_idle(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            app.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (None, 0.0)
            app.on_key_press(FAKE_ALT_R)
        assert app._pending_title == TITLE_IDLE
