from unittest.mock import MagicMock, patch

from talk_to_vibe.audio.recorder import AudioRecorder


class TestAudioRecorder:
    def test_start_reports_error_via_callback(self):
        errors = []
        failing_stream = MagicMock()
        failing_stream.start.side_effect = __import__("sounddevice").PortAudioError("denied")
        retry_stream = MagicMock()
        retry_stream.start.side_effect = __import__("sounddevice").PortAudioError("still denied")

        with patch(
            "talk_to_vibe.audio.recorder.find_real_microphone",
            side_effect=[(1, "Mic A"), (2, "Mic B"), (3, "Mic C")],
        ), patch(
            "talk_to_vibe.audio.recorder.sd.InputStream",
            side_effect=[failing_stream, retry_stream],
        ), patch("talk_to_vibe.audio.recorder.sd._terminate") as mock_terminate, patch(
            "talk_to_vibe.audio.recorder.sd._initialize"
        ) as mock_initialize:
            recorder = AudioRecorder(error_callback=errors.append)
            assert recorder.start() is False

        assert len(errors) == 1
        assert "Microphone error" in errors[0]
        assert "still denied" in errors[0]
        mock_terminate.assert_called_once_with()
        mock_initialize.assert_called_once_with()

    def test_start_without_callback_prints_message(self, capsys):
        failing_stream = MagicMock()
        failing_stream.start.side_effect = __import__("sounddevice").PortAudioError("denied")
        retry_stream = MagicMock()
        retry_stream.start.side_effect = __import__("sounddevice").PortAudioError("still denied")

        with patch(
            "talk_to_vibe.audio.recorder.find_real_microphone",
            side_effect=[(1, "Mic A"), (2, "Mic B"), (3, "Mic C")],
        ), patch(
            "talk_to_vibe.audio.recorder.sd.InputStream",
            side_effect=[failing_stream, retry_stream],
        ), patch("talk_to_vibe.audio.recorder.sd._terminate"), patch(
            "talk_to_vibe.audio.recorder.sd._initialize"
        ):
            recorder = AudioRecorder()
            assert recorder.start() is False

        captured = capsys.readouterr()
        assert "Microphone error" in captured.out

    def test_start_failure_refreshes_input_device_and_clears_stream(self):
        failing_stream = MagicMock()
        failing_stream.start.side_effect = __import__("sounddevice").PortAudioError("denied")
        retry_stream = MagicMock()
        retry_stream.start.side_effect = __import__("sounddevice").PortAudioError("still denied")

        with patch(
            "talk_to_vibe.audio.recorder.find_real_microphone",
            side_effect=[(1, "Mic A"), (2, "Mic B"), (3, "Mic C")],
        ), patch(
            "talk_to_vibe.audio.recorder.sd.InputStream",
            side_effect=[failing_stream, retry_stream],
        ), patch("talk_to_vibe.audio.recorder.sd._terminate") as mock_terminate, patch(
            "talk_to_vibe.audio.recorder.sd._initialize"
        ) as mock_initialize:
            recorder = AudioRecorder()

            assert recorder.start() is False

        assert recorder.stream is None
        assert recorder.device_id == 3
        assert recorder.device_name == "Mic C"
        failing_stream.close.assert_called_once_with()
        retry_stream.close.assert_called_once_with()
        mock_terminate.assert_called_once_with()
        mock_initialize.assert_called_once_with()

    def test_start_retries_after_backend_reset_and_recovers(self):
        failing_stream = MagicMock()
        failing_stream.start.side_effect = __import__("sounddevice").PortAudioError(
            "Error opening InputStream: Internal PortAudio error [PaErrorCode -9986]"
        )
        recovered_stream = MagicMock()

        with patch(
            "talk_to_vibe.audio.recorder.find_real_microphone",
            side_effect=[(1, "Mic A"), (2, "Mic B"), (3, "Mic C")],
        ), patch(
            "talk_to_vibe.audio.recorder.sd.InputStream",
            side_effect=[failing_stream, recovered_stream],
        ):
            with patch("talk_to_vibe.audio.recorder.sd._terminate") as mock_terminate, patch(
                "talk_to_vibe.audio.recorder.sd._initialize"
            ) as mock_initialize:
                recorder = AudioRecorder()

                assert recorder.start() is True

        assert recorder.stream is recovered_stream
        assert recorder.device_id == 3
        assert recorder.device_name == "Mic C"
        failing_stream.close.assert_called_once_with()
        recovered_stream.start.assert_called_once_with()
        mock_terminate.assert_called_once_with()
        mock_initialize.assert_called_once_with()
