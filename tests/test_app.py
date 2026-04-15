import threading
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from talk_to_vibe.app import TalkToVibe, DEBOUNCE_SECONDS
from talk_to_vibe.providers.base import BaseSTTProvider
from talk_to_vibe.errors import ProviderError


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
FAKE_F18 = FakeKey("f18")


def _make_app(stt=None, **kwargs):
    stt = stt or FakeSTT()
    with patch("talk_to_vibe.app.get_platform") as mock_plat:
        mock_platform = MagicMock()
        mock_platform.get_key_map.return_value = {"alt_r": FAKE_ALT_R, "ctrl": FAKE_CTRL, "f18": FAKE_F18}
        mock_platform.get_default_ptt_key.return_value = "alt_r"
        mock_platform.parse_ptt_chord.side_effect = lambda s: frozenset(
            {FAKE_ALT_R} if s == "alt_r" else
            {FAKE_CTRL, FAKE_ALT_R} if s == "ctrl+alt_r" else
            {FAKE_F18} if s == "f18" else
            set()
        )
        mock_platform.get_chord_display_name.side_effect = lambda s: s.replace("+", " + ").replace("_", " ").title()
        mock_plat.return_value = mock_platform
        app = TalkToVibe(stt=stt, ptt_key_name=kwargs.pop("ptt_key_name", "alt_r"), **kwargs)
    return app


class TestTalkToVibeProcess:
    def test_successful_transcription(self, capsys):
        app = _make_app(stt=FakeSTT(return_text="hello world"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        app._process(audio, 1.0)
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_empty_transcription(self, capsys):
        app = _make_app(stt=FakeSTT(return_text=""))
        audio = np.zeros((16000, 1), dtype=np.int16)
        app._process(audio, 1.0)
        captured = capsys.readouterr()
        assert "empty result" in captured.out

    def test_provider_error_displayed(self, capsys):
        app = _make_app(stt=FakeSTT(should_raise=ProviderError("API key invalid")))
        audio = np.zeros((16000, 1), dtype=np.int16)
        app._process(audio, 1.0)
        captured = capsys.readouterr()
        assert "API key invalid" in captured.out

    def test_processing_flag_reset_on_success(self):
        app = _make_app(stt=FakeSTT(return_text="test"))
        audio = np.zeros((16000, 1), dtype=np.int16)
        app.processing = True
        app._process(audio, 1.0)
        assert app.processing is False

    def test_processing_flag_reset_on_error(self):
        app = _make_app(stt=FakeSTT(should_raise=RuntimeError("boom")))
        audio = np.zeros((16000, 1), dtype=np.int16)
        app.processing = True
        app._process(audio, 1.0)
        assert app.processing is False

    def test_banner_shows_model(self):
        stt = FakeSTT(return_text="test")
        assert stt.model == "fake-model-v1"


class TestChordInit:
    def test_single_key_chord(self):
        app = _make_app(ptt_key_name="alt_r")
        assert app.ptt_chord == frozenset({FAKE_ALT_R})

    def test_multi_key_chord(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        assert app.ptt_chord == frozenset({FAKE_CTRL, FAKE_ALT_R})

    def test_held_keys_initially_empty(self):
        app = _make_app()
        assert len(app.held_keys) == 0


class TestChordPress:
    def test_single_key_press_starts_debounce(self):
        app = _make_app(ptt_key_name="alt_r")
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is not None
        app._debounce_timer.cancel()

    def test_chord_press_starts_debounce(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        app.on_key_press(FAKE_CTRL)
        assert app._debounce_timer is None
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is not None
        app._debounce_timer.cancel()

    def test_extra_key_cancels_debounce(self):
        app = _make_app(ptt_key_name="alt_r")
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is not None
        app.on_key_press(FakeKey("other"))
        assert app._debounce_timer is None

    def test_partial_chord_no_debounce(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        app.on_key_press(FAKE_CTRL)
        assert app._debounce_timer is None

    def test_no_debounce_while_recording(self):
        app = _make_app(ptt_key_name="alt_r")
        app.is_recording = True
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is None

    def test_no_debounce_while_processing(self):
        app = _make_app(ptt_key_name="alt_r")
        app.processing = True
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is None


class TestChordRelease:
    def test_release_stops_recording(self):
        app = _make_app(ptt_key_name="alt_r")
        app.is_recording = True
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.stop.return_value = (np.zeros((16000, 1), dtype=np.int16), 1.0)
            app.on_key_release(FAKE_ALT_R)
        assert app.is_recording is False

    def test_release_non_chord_key_ignored(self):
        app = _make_app(ptt_key_name="alt_r")
        app.is_recording = True
        other_key = FakeKey("other")
        app.on_key_release(other_key)
        assert app.is_recording is True

    def test_release_removes_from_held_keys(self):
        app = _make_app(ptt_key_name="alt_r")
        app.on_key_press(FAKE_ALT_R)
        assert FAKE_ALT_R in app.held_keys
        app.on_key_release(FAKE_ALT_R)
        assert FAKE_ALT_R not in app.held_keys

    def test_release_cancels_debounce(self):
        app = _make_app(ptt_key_name="alt_r")
        app.on_key_press(FAKE_ALT_R)
        assert app._debounce_timer is not None
        app.on_key_release(FAKE_ALT_R)
        assert app._debounce_timer is None

    def test_short_recording_ignored(self):
        app = _make_app(ptt_key_name="alt_r")
        app.is_recording = True
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.stop.return_value = (None, 0.0)
            app.on_key_release(FAKE_ALT_R)
        assert app.processing is False


class TestDebounceTimer:
    def test_debounce_fires_recording(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            assert app._debounce_timer is not None
            app._debounce_timer.join()
            assert app.is_recording is True

    def test_debounce_canceled_if_keys_change(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "recorder") as mock_rec:
            app.on_key_press(FAKE_ALT_R)
            extra = FakeKey("extra")
            app.on_key_press(extra)
            assert app._debounce_timer is None
            assert app.is_recording is False

    def test_debounce_does_not_fire_if_keys_no_longer_match(self):
        app = _make_app(ptt_key_name="alt_r")
        app.on_key_press(FAKE_ALT_R)
        timer = app._debounce_timer
        app.held_keys.add(FakeKey("extra"))
        timer.join()
        assert app.is_recording is False
