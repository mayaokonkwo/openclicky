"""The recorder with a shell command standing in for parecord: it writes known bytes, then waits
to be stopped, the way a real recorder streams until SIGINT."""

import io
import time
import wave

import pytest

from openclicky_linux.recorder import MicrophoneRecording, RecorderUnavailable, pcm_seconds, wav_from_pcm

# 3 bytes: the odd one must be dropped (a signal can land mid-sample).
STREAMS_THEN_WAITS = ("sh", "-c", "printf 'abc'; exec sleep 30")
DIES_AT_ONCE = ("sh", "-c", "echo 'no such device' >&2; exit 1")


def test_stop_returns_whole_samples_of_what_was_recorded():
    recording = MicrophoneRecording(STREAMS_THEN_WAITS)
    time.sleep(0.2)
    started = time.monotonic()
    assert recording.stop() == b"ab"
    assert time.monotonic() - started < 2


def test_a_recorder_that_dies_says_why():
    recording = MicrophoneRecording(DIES_AT_ONCE)
    time.sleep(0.2)
    with pytest.raises(RecorderUnavailable, match="no such device"):
        recording.stop()


def test_cancel_ends_the_recorder():
    recording = MicrophoneRecording(STREAMS_THEN_WAITS)
    recording.cancel()
    assert recording._process.poll() is not None


def test_the_wav_is_16_khz_mono_16_bit():
    pcm = b"\x01\x00" * 16_000
    assert pcm_seconds(pcm) == 1.0
    with wave.open(io.BytesIO(wav_from_pcm(pcm))) as wav_file:
        assert (wav_file.getframerate(), wav_file.getnchannels(), wav_file.getsampwidth(), wav_file.getnframes()) == (16_000, 1, 2, 16_000)
