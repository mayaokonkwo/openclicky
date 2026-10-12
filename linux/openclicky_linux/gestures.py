"""The dictation key's gestures, from raw key downs and ups: the Mac app's
`CompanionShortcutRecognizer`, dictation part only, with the same timings.

- held and released → a take that ends on release
- tapped (released within `TAP_MAX_HOLD_SECONDS`) → a take that listens until the next tap
- tapped twice quickly → cancel
- esc → cancel
- another key pressed while the dictation key is held (right ctrl + C) → that was a shortcut, the
  release says so and the take is thrown away
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


ShortcutEvent = DictationPressed | DictationReleased | DictationDoubleTapped | EscapePressed


class DictationGestureRecognizer:
    def __init__(self) -> None:
        self.is_dictation_key_down = False
        self._pressed_at = 0.0
        self._other_key_pressed_during_hold = False
        self._last_tap_released_at: float | None = None

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
        return [EscapePressed()] if is_escape else []
