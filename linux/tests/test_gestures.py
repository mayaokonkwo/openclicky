from openclicky_linux.gestures import (
    DictationDoubleTapped, DictationGestureRecognizer, DictationPressed, DictationReleased, EscapePressed,
)


def test_a_hold_is_a_press_and_a_release_that_is_not_a_tap():
    recognizer = DictationGestureRecognizer()
    assert recognizer.dictation_key_down(10.0) == [DictationPressed()]
    assert recognizer.dictation_key_up(11.5) == [DictationReleased(was_tap=False)]


def test_auto_repeat_downs_are_ignored():
    recognizer = DictationGestureRecognizer()
    recognizer.dictation_key_down(10.0)
    assert recognizer.dictation_key_down(10.5) == []


def test_two_quick_taps_are_a_double_tap():
    recognizer = DictationGestureRecognizer()
    recognizer.dictation_key_down(10.0)
    assert recognizer.dictation_key_up(10.1) == [DictationReleased(was_tap=True)]
    recognizer.dictation_key_down(10.3)
    assert recognizer.dictation_key_up(10.4) == [DictationReleased(was_tap=True), DictationDoubleTapped()]


def test_taps_far_apart_are_not_a_double_tap():
    recognizer = DictationGestureRecognizer()
    recognizer.dictation_key_down(10.0)
    recognizer.dictation_key_up(10.1)
    recognizer.dictation_key_down(13.0)
    assert recognizer.dictation_key_up(13.1) == [DictationReleased(was_tap=True)]


def test_a_key_typed_while_held_marks_the_release():
    recognizer = DictationGestureRecognizer()
    recognizer.dictation_key_down(10.0)
    assert recognizer.other_key_down(is_escape=False) == []
    assert recognizer.dictation_key_up(10.1) == [DictationReleased(was_tap=False, key_was_pressed_during_hold=True)]


def test_escape_is_reported():
    assert DictationGestureRecognizer().other_key_down(is_escape=True) == [EscapePressed()]
