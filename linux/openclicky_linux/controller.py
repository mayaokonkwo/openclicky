"""One take at a time, the Mac app's `DictationTakeController` in small: idle → listening →
finishing. Press opens the microphone and remembers the window in front; release stops it, the
audio is transcribed off the main thread, formatted, and pasted into that window — only that
window: if another one is in front by then, the words go to the clipboard instead. Every
continuation carries the take's id, so a cancelled take never pastes into the next.

The desktop is reached only through `DictationHost`, so the tests run takes with fakes.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from . import formatter
from .gestures import DictationDoubleTapped, DictationPressed, DictationReleased, EscapePressed, ShortcutEvent
from .recorder import pcm_seconds, wav_from_pcm
from .space import DictationSpace

# Shorter than this the take was a slip of the finger, not speech.
MINIMUM_SPEECH_SECONDS = 0.3


class TakeState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    FINISHING = "finishing"


@dataclass(frozen=True)
class FocusedWindow:
    window_id: int
    app_class: str | None = None
    is_terminal: bool = False


class Recording(Protocol):
    def stop(self) -> bytes: ...
    def cancel(self) -> None: ...


@dataclass
class DictationHost:
    start_recording: Callable[[], Recording]
    transcribe: Callable[[bytes], str]
    focused_window: Callable[[], FocusedWindow | None]
    # True when the paste keystroke was sent; False leaves the words on the clipboard.
    paste: Callable[[str, FocusedWindow | None], bool]
    copy_to_clipboard: Callable[[str], None]
    load_space: Callable[[], DictationSpace]
    # Runs `work` off the main thread, then `done(result_or_exception)` back on it.
    run_in_background: Callable[[Callable[[], Any], Callable[[Any], None]], None]
    # Calls `action` on the main thread after `seconds`.
    schedule: Callable[[float, Callable[[], None]], None]


class OrbModel:
    """What the orb shows: a phase ("idle", "listening", "working", "done", "failed") and one line."""

    def __init__(self) -> None:
        self.phase = "idle"
        self.message: str | None = None
        self.listeners: list[Callable[["OrbModel"], None]] = []

    def show(self, phase: str, message: str | None = None) -> None:
        self.phase = phase
        self.message = message
        for listener in list(self.listeners):
            listener(self)


class DictationTakeController:
    def __init__(self, host: DictationHost, orb: OrbModel) -> None:
        self.host = host
        self.orb = orb
        self.state = TakeState.IDLE
        self._take_ids = itertools.count(1)
        self.take_id = 0
        self._take_is_toggle = False
        self._recording: Recording | None = None
        self._window_at_press: FocusedWindow | None = None
        # Every take's outcome, newest last: the tests and the log read it.
        self.finished_takes: list[tuple[str, str]] = []

    @property
    def is_take_in_progress(self) -> bool:
        return self.state is not TakeState.IDLE

    def handle(self, event: ShortcutEvent) -> None:
        if isinstance(event, DictationPressed):
            if self.state is TakeState.IDLE:
                self._begin_take()
            elif self.state is TakeState.LISTENING and self._take_is_toggle:
                # A second press while a tapped take listens: this press ends it.
                self._stop_take()
        elif isinstance(event, DictationReleased):
            if self.state is not TakeState.LISTENING or self._take_is_toggle:
                return
            if event.key_was_pressed_during_hold:
                # The key was held for a shortcut (right ctrl + C), not to talk.
                self.cancel_take("cancelled, that was a shortcut")
            elif event.was_tap:
                self._take_is_toggle = True
                self.orb.show("listening", "say it, then tap the key again")
            else:
                self._stop_take()
        elif isinstance(event, DictationDoubleTapped):
            if self.is_take_in_progress:
                self.cancel_take("cancelled")
        elif isinstance(event, EscapePressed):
            if self.is_take_in_progress:
                self.cancel_take("cancelled")

    def _begin_take(self) -> None:
        self.take_id = next(self._take_ids)
        self._take_is_toggle = False
        self._window_at_press = self.host.focused_window()
        try:
            self._recording = self.host.start_recording()
        except Exception as failure:  # noqa: BLE001 - any failure to open the microphone ends the take the same way
            self.state = TakeState.LISTENING
            self._fail(str(failure) or "couldn't open the microphone", self.take_id)
            return
        self.state = TakeState.LISTENING
        self.orb.show("listening", "release to transcribe")

    def _stop_take(self) -> None:
        if self.state is not TakeState.LISTENING or self._recording is None:
            return
        this_take_id = self.take_id
        recording = self._recording
        self._recording = None
        self.state = TakeState.FINISHING
        self.orb.show("working", "moving your words")
        transcribe = self.host.transcribe

        def hear_the_take() -> str:
            pcm = recording.stop()
            if pcm_seconds(pcm) < MINIMUM_SPEECH_SECONDS:
                return ""
            return transcribe(wav_from_pcm(pcm))

        self.host.run_in_background(hear_the_take, lambda outcome: self._finish_take(outcome, this_take_id))

    def cancel_take(self, reason: str) -> None:
        if not self.is_take_in_progress:
            return
        if self._recording is not None:
            self._recording.cancel()
            self._recording = None
        self._end_take()
        self._show_then_rest("failed", reason, after_seconds=1.4)

    def _finish_take(self, outcome: Any, this_take_id: int) -> None:
        # Cancelled, or another take began, while the engine was at work: these words are dropped.
        if self.take_id != this_take_id or self.state is not TakeState.FINISHING:
            return
        if isinstance(outcome, BaseException):
            self._fail(str(outcome) or "couldn't transcribe that", this_take_id)
            return
        text = formatter.format_locally(outcome or "", self.host.load_space())
        if not text:
            self._fail("didn't catch that", this_take_id)
            return
        message = self._deliver(text)
        self.finished_takes.append((text, message))
        self._end_take()
        self._show_then_rest("done", message, after_seconds=1.8)

    def _deliver(self, text: str) -> str:
        """Pasted into the window that was in front at press, and only there."""
        window_now = self.host.focused_window()
        window_at_press = self._window_at_press
        if window_at_press is not None and window_now is not None and window_now.window_id != window_at_press.window_id:
            self.host.copy_to_clipboard(text)
            return "the window changed. copied, press ctrl+v"
        if self.host.paste(text, window_now or window_at_press):
            return "moved to text box"
        self.host.copy_to_clipboard(text)
        return "copied, press ctrl+v"

    def _fail(self, message: str, failed_take_id: int) -> None:
        if self.take_id != failed_take_id or not self.is_take_in_progress:
            return
        if self._recording is not None:
            self._recording.cancel()
            self._recording = None
        self.finished_takes.append(("", message))
        self._end_take()
        self._show_then_rest("failed", message, after_seconds=2.5)

    def _end_take(self) -> None:
        self.state = TakeState.IDLE
        self._take_is_toggle = False

    def _show_then_rest(self, phase: str, message: str, after_seconds: float) -> None:
        self.orb.show(phase, message)
        shown_for_take_id = self.take_id

        def rest() -> None:
            if self.take_id == shown_for_take_id and self.state is TakeState.IDLE:
                self.orb.show("idle")

        self.host.schedule(after_seconds, rest)
