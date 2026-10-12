"""The microphone, through the recorder every desktop already has: `parecord` (PulseAudio, and
PipeWire through pipewire-pulse) or `arecord` (ALSA). Raw 16 kHz mono 16-bit PCM on stdout,
which is what the transcription APIs want once it has a WAV header. A command-line recorder
instead of a Python audio library: nothing to compile, and the desktop's own default input is used.
"""

from __future__ import annotations

import io
import shutil
import signal
import subprocess
import threading
import wave

SAMPLE_RATE = 16_000
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1

RECORDER_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("parecord", "--raw", f"--rate={SAMPLE_RATE}", f"--channels={CHANNELS}", "--format=s16le"),
    ("arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS)),
)


class RecorderUnavailable(Exception):
    pass


def find_recorder_command() -> tuple[str, ...]:
    for command in RECORDER_COMMANDS:
        if shutil.which(command[0]):
            return command
    raise RecorderUnavailable("no microphone recorder found. install pulseaudio-utils (parecord) or alsa-utils (arecord)")


def pcm_seconds(pcm: bytes) -> float:
    return len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH_BYTES * CHANNELS)


def wav_from_pcm(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


class MicrophoneRecording:
    """One take's audio: started at press, stopped (or cancelled) at release."""

    def __init__(self, command: tuple[str, ...] | None = None) -> None:
        self._process = subprocess.Popen(command or find_recorder_command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._chunks: list[bytes] = []
        # The pipe is drained all the time: a full pipe would stall the recorder mid-take.
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()

    def _drain(self) -> None:
        assert self._process.stdout is not None
        for chunk in iter(lambda: self._process.stdout.read(4096), b""):
            self._chunks.append(chunk)

    def _end_process(self) -> None:
        if self._process.poll() is None:
            # SIGINT lets the recorder flush what it has; SIGKILL only if it ignores that.
            self._process.send_signal(signal.SIGINT)
            try:
                self._process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        self._reader.join(timeout=1.0)

    def stop(self) -> bytes:
        """The PCM heard so far. Raises when the recorder died on its own (no microphone, refused)."""
        exited_early = self._process.poll() is not None
        self._end_process()
        pcm = b"".join(self._chunks)
        if exited_early and not pcm:
            error_output = (self._process.stderr.read() if self._process.stderr else b"").decode(errors="replace").strip()
            raise RecorderUnavailable(f"the microphone recorder stopped: {error_output or 'no output'}")
        # Whole samples only: a signal can land mid-sample.
        return pcm[: len(pcm) - len(pcm) % SAMPLE_WIDTH_BYTES]

    def cancel(self) -> None:
        self._end_process()
        self._chunks.clear()
