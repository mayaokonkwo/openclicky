"""The dictation key's gestures, from raw key downs and ups: the Mac app's
`CompanionShortcutRecognizer`, dictation part only, with the same timings.

- held and released → a take that ends on release
- tapped (released within `TAP_MAX_HOLD_SECONDS`) → a take that listens until the next tap
- tapped twice quickly → cancel
- esc → cancel
- another key pressed while the dictation key is held (right ctrl + C) → that was a shortcut, the
  release says so and the take is thrown away
- the composer key (left ctrl) tapped twice → the ask box opens (the Mac's ⌃ ×2); a tap is a quick
  press and release with no other key in between, so ctrl+C never counts
Pure: fed with timestamps, so it is tested without a keyboard.
"""

from __future__ import annotations

from dataclasses import dataclass

TAP_MAX_HOLD_SECONDS = 0.35
DOUBLE_TAP_WINDOW_SECONDS = 0.45


@dataclass(frozen=True)
class DictationPressed:
    pass


@dataclass(frozen=True)
class DictationReleased:
    was_tap: bool
    key_was_pressed_during_hold: bool = False


@dataclass(frozen=True)
class DictationDoubleTapped:
    pass


@dataclass(frozen=True)
class EscapePressed:
    pass


@dataclass(frozen=True)
class TextComposerRequested:
    pass


ShortcutEvent = DictationPressed | DictationReleased | DictationDoubleTapped | EscapePressed | TextComposerRequested


class DictationGestureRecognizer:
    def __init__(self) -> None:
        self.is_dictation_key_down = False
        self._pressed_at = 0.0
        self._other_key_pressed_during_hold = False
        self._last_tap_released_at: float | None = None
        self._composer = _DoubleTapDetector()

    def dictation_key_down(self, at_seconds: float) -> list[ShortcutEvent]:
        # Auto-repeat sends more downs while the key is held: only the first counts.
        if self.is_dictation_key_down:
            return []
        self.is_dictation_key_down = True
        self._pressed_at = at_seconds
        self._other_key_pressed_during_hold = False
        return [DictationPressed()]

    def dictation_key_up(self, at_seconds: float) -> list[ShortcutEvent]:
        if not self.is_dictation_key_down:
            return []
        self.is_dictation_key_down = False
        was_tap = at_seconds - self._pressed_at <= TAP_MAX_HOLD_SECONDS and not self._other_key_pressed_during_hold
        events: list[ShortcutEvent] = [DictationReleased(was_tap=was_tap, key_was_pressed_during_hold=self._other_key_pressed_during_hold)]
        if was_tap:
            if self._last_tap_released_at is not None and at_seconds - self._last_tap_released_at <= DOUBLE_TAP_WINDOW_SECONDS:
                events.append(DictationDoubleTapped())
                self._last_tap_released_at = None
            else:
                self._last_tap_released_at = at_seconds
        else:
            self._last_tap_released_at = None
        return events

    def other_key_down(self, is_escape: bool) -> list[ShortcutEvent]:
        if self.is_dictation_key_down:
            self._other_key_pressed_during_hold = True
        # A key between two taps breaks the double tap.
        self._last_tap_released_at = None
        self._composer.other_key_down()
        return [EscapePressed()] if is_escape else []

    def composer_key_down(self, at_seconds: float) -> list[ShortcutEvent]:
        self._composer.key_down(at_seconds)
        return []

    def composer_key_up(self, at_seconds: float) -> list[ShortcutEvent]:
        return [TextComposerRequested()] if self._composer.key_up(at_seconds) else []


class _DoubleTapDetector:
    """Two taps (quick press and release, nothing else typed) within the double-tap window."""

    def __init__(self) -> None:
        self._is_down = False
        self._pressed_at = 0.0
        self._interrupted = False
        self._last_tap_released_at: float | None = None

    def key_down(self, at_seconds: float) -> None:
        if self._is_down:
            return
        self._is_down = True
        self._pressed_at = at_seconds
        self._interrupted = False

    def other_key_down(self) -> None:
        self._interrupted = True
        self._last_tap_released_at = None

    def key_up(self, at_seconds: float) -> bool:
        """True on the release that completes a double tap."""
        if not self._is_down:
            return False
        self._is_down = False
        was_tap = at_seconds - self._pressed_at <= TAP_MAX_HOLD_SECONDS and not self._interrupted
        if not was_tap:
            self._last_tap_released_at = None
            return False
        if self._last_tap_released_at is not None and at_seconds - self._last_tap_released_at <= DOUBLE_TAP_WINDOW_SECONDS:
            self._last_tap_released_at = None
            return True
        self._last_tap_released_at = at_seconds
        return False
