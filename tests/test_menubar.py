import signal
import threading
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

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
    mock_platform.get_key_map.return_value = {"alt_r": FAKE_ALT_R, "ctrl": FAKE_CTRL}
    mock_platform.get_default_ptt_key.return_value = "alt_r"
    mock_platform.parse_ptt_chord.side_effect = lambda s: frozenset(
        {FAKE_ALT_R} if s == "alt_r" else
        {FAKE_CTRL, FAKE_ALT_R} if s == "ctrl+alt_r" else set()
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
        assert app.ptt_chord == frozenset({FAKE_ALT_R})

    def test_multi_key_chord(self):
        app = _make_menubar_app(ptt_key_name="ctrl+alt_r")
        assert app.ptt_chord == frozenset({FAKE_CTRL, FAKE_ALT_R})

    def test_held_keys_initially_empty(self):
        app = _make_menubar_app()
        assert len(app.held_keys) == 0

    def test_paste_in_progress_initially_false(self):
        app = _make_menubar_app()
        assert app._paste_in_progress is False

    def test_prompt_file_stored(self):
        app = _make_menubar_app(prompt_file="~/my_prompt.md")
        assert app.prompt_file == "~/my_prompt.md"


class TestMenuBarChordPress:
    def test_press_starts_debounce(self):
        app = _make_menubar_app()
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is not None
        app._debounce_timer.cancel()

    def test_extra_key_cancels_debounce(self):
        app = _make_menubar_app()
        app.on_key_press(FAKE_ALT_R)
        app.on_key_press(FakeKey("extra"))
        assert app._debounce_timer is None

    def test_partial_chord_no_debounce(self):
        app = _make_menubar_app(ptt_key_name="ctrl+alt_r")
        app.on_key_press(FAKE_CTRL)
        assert app._debounce_timer is None


class TestMenuBarChordRelease:
    def test_release_stops_recording(self):
        app = _make_menubar_app()
        app.is_recording = True
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.stop.return_value = (np.zeros((16000, 1), dtype=np.int16), 1.0)
            app.on_key_release(FAKE_ALT_R)
        assert app.is_recording is False

    def test_release_cancels_debounce(self):
        app = _make_menubar_app()
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is not None
        app.on_key_release(FAKE_ALT_R)
        assert app._debounce_timer is None

    def test_release_removes_from_held_keys(self):
        app = _make_menubar_app()
        app.on_key_press(FAKE_ALT_R)
        assert FAKE_ALT_R in app.held_keys
        app.on_key_release(FAKE_ALT_R)
        assert FAKE_ALT_R not in app.held_keys

    def test_short_recording_ignored(self):
        app = _make_menubar_app()
        app.is_recording = True
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.stop.return_value = (None, 0.0)
            app.on_key_release(FAKE_ALT_R)
        assert app.processing is False


class TestMenuBarDebounce:
    def test_debounce_fires_recording(self):
        app = _make_menubar_app()
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            app._debounce_timer.join()
            assert app.is_recording is True


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

    def test_cleanup_cancels_debounce_timer(self):
        app = _make_menubar_app()
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is not None
        app._cleanup()
        assert app._debounce_timer is None

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
        assert app._debounce_timer is None


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
            app._debounce_timer.join()
        assert app._pending_title == TITLE_RECORDING

    def test_transcribing_queues_title(self):
        app = _make_menubar_app()
        app.is_recording = True
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.stop.return_value = (np.zeros((16000, 1), dtype=np.int16), 1.0)
            app.on_key_release(FAKE_ALT_R)
        assert app._pending_title == TITLE_TRANSCRIBING

    def test_short_recording_queues_idle(self):
        app = _make_menubar_app()
        app.is_recording = True
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.stop.return_value = (None, 0.0)
            app.on_key_release(FAKE_ALT_R)
        assert app._pending_title == TITLE_IDLE
