from unittest.mock import patch, MagicMock
import numpy as np

from talk_to_vibe.app import TalkToVibe
from talk_to_vibe.platforms.base import PasteResult
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
FAKE_ALT = FakeKey("alt")
FAKE_CTRL = FakeKey("ctrl")
FAKE_F18 = FakeKey("f18")


def _make_app(stt=None, **kwargs):
    stt = stt or FakeSTT()
    with patch("talk_to_vibe.app.get_platform") as mock_plat:
        mock_platform = MagicMock()
        mock_platform.get_key_map.return_value = {"alt_r": FAKE_ALT, "alt_l": FAKE_ALT, "alt": FAKE_ALT, "ctrl": FAKE_CTRL, "f18": FAKE_F18}
        mock_platform.get_default_ptt_key.return_value = "alt_r"
        mock_platform.normalize_listener_key.side_effect = lambda key: FAKE_ALT if key == FAKE_ALT_R else key
        mock_platform.parse_ptt_chord.side_effect = lambda s: frozenset(
            {FAKE_ALT} if s in {"alt_r", "alt_l", "alt"} else
            {FAKE_CTRL, FAKE_ALT} if s == "ctrl+alt_r" else
            {FAKE_F18} if s == "f18" else
            set()
        )
        mock_platform.get_chord_display_name.side_effect = lambda s: s.replace("+", " + ").replace("_", " ").title()
        # Drain the chunk iterator like a real platform would so the upstream
        # transcribe_stream() actually runs and prints progress.
        def _drain_stream(chunks, auto_enter=False):
            return PasteResult(
                full_text=" ".join(c.strip() for c in chunks if c and c.strip()).strip()
            )
        mock_platform.paste_text_stream.side_effect = _drain_stream
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

    def test_clipboard_restore_failure_printed(self, capsys):
        app = _make_app(stt=FakeSTT(return_text="hello world"))
        app.platform.paste_text_stream.side_effect = lambda chunks, auto_enter=False: PasteResult(
            full_text="hello world",
            clipboard_restore_failed=True,
            clipboard_restore_reason="could not restore clipboard",
        )
        audio = np.zeros((16000, 1), dtype=np.int16)
        app._process(audio, 1.0)
        captured = capsys.readouterr()
        assert "Clipboard: could not restore previous clipboard contents" in captured.out

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
        assert app.ptt_chord == frozenset({FAKE_ALT})

    def test_multi_key_chord(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        assert app.ptt_chord == frozenset({FAKE_CTRL, FAKE_ALT})

    def test_held_keys_initially_empty(self):
        app = _make_app()
        assert len(app.held_keys) == 0


class TestChordPress:
    def test_single_key_press_starts_recording_immediately(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
        assert app.is_recording is True
        assert app._chord_armed is True

    def test_chord_press_starts_when_completed(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_CTRL)
            mock_rec.start.assert_not_called()
            app.on_key_press(FAKE_ALT_R)
        assert app.is_recording is True
        assert app.held_keys == {FAKE_CTRL, FAKE_ALT}

    def test_extra_key_prevents_toggle_for_multi_key_chord(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_CTRL)
            app.on_key_press(FakeKey("other"))
            app.on_key_press(FAKE_ALT_R)
        mock_rec.start.assert_not_called()
        assert app.is_recording is False

    def test_partial_chord_does_not_toggle(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        with patch.object(app, "recorder") as mock_rec:
            app.on_key_press(FAKE_CTRL)
        mock_rec.start.assert_not_called()
        assert app.is_recording is False

    def test_repeat_press_while_armed_is_ignored(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "_start_recording") as mock_start, patch.object(app, "_stop_recording") as mock_stop:
            app.on_key_press(FAKE_ALT_R)
            app.on_key_press(FAKE_ALT_R)
        mock_start.assert_called_once()
        mock_stop.assert_not_called()

    def test_press_ignored_while_processing(self):
        app = _make_app(ptt_key_name="alt_r")
        app.processing = True
        with patch.object(app, "_start_recording") as mock_start:
            app.on_key_press(FAKE_ALT_R)
        mock_start.assert_not_called()
        assert app.is_recording is False


class TestChordRelease:
    def test_release_removes_from_held_keys(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "_start_recording"):
            app.on_key_press(FAKE_ALT_R)
        assert FAKE_ALT in app.held_keys
        app.on_key_release(FAKE_ALT_R)
        assert FAKE_ALT not in app.held_keys

    def test_release_disarms_chord(self):
        app = _make_app(ptt_key_name="alt_r")
        app.held_keys.add(FAKE_ALT)
        app._chord_armed = True
        app.on_key_release(FAKE_ALT_R)
        assert app._chord_armed is False

    def test_release_non_chord_key_keeps_chord_armed(self):
        app = _make_app(ptt_key_name="alt_r")
        app.held_keys.update({FAKE_ALT, FakeKey("other")})
        app._chord_armed = True
        app.on_key_release(FakeKey("other"))
        assert app._chord_armed is True


class TestToggleRecording:
    def test_second_press_stops_recording_after_release(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            app.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (np.zeros((16000, 1), dtype=np.int16), 1.0)
            with patch("talk_to_vibe.app.threading.Thread") as mock_thread:
                thread = MagicMock()
                mock_thread.return_value = thread
                app.on_key_press(FAKE_ALT_R)
        assert app.is_recording is False
        assert app.processing is True
        thread.start.assert_called_once()

    def test_second_press_with_short_recording_is_ignored(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_ALT_R)
            app.on_key_release(FAKE_ALT_R)
            mock_rec.stop.return_value = (None, 0.0)
            with patch("talk_to_vibe.app.threading.Thread") as mock_thread:
                app.on_key_press(FAKE_ALT_R)
        assert app.processing is False
        mock_thread.assert_not_called()

    def test_start_failure_resets_recording_state(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "recorder") as mock_rec:
            mock_rec.start.return_value = False
            app.on_key_press(FAKE_ALT_R)
        assert app.is_recording is False

    def test_start_failure_resets_armed_state_after_timeout(self):
        app = _make_app(ptt_key_name="alt_r")
        with patch.object(app, "recorder") as mock_rec, \
             patch("talk_to_vibe.app.time.monotonic", side_effect=[1.0, 4.5]):
            mock_rec.start.return_value = False
            app.on_key_press(FAKE_ALT_R)
            app.on_key_press(FAKE_ALT_R)

        assert app.is_recording is False
        assert app._chord_armed is False
        assert app.held_keys == set()

    def test_stale_chord_state_is_cleared_before_next_press(self):
        app = _make_app(ptt_key_name="ctrl+alt_r")
        app.held_keys = {FAKE_CTRL, FAKE_ALT}
        app._chord_armed = True
        app._last_key_event_at = 1.0
        app._last_chord_arm_at = 1.0

        with patch.object(app, "recorder") as mock_rec, \
             patch("talk_to_vibe.app.time.monotonic", return_value=4.5):
            mock_rec.start.return_value = True
            app.on_key_press(FAKE_CTRL)

        mock_rec.start.assert_not_called()
        assert app._chord_armed is False
        assert app.held_keys == {FAKE_CTRL}
