"""Asking by text, one question at a time: left ctrl tapped twice opens the ask box; Enter sends the
question with a screenshot; the pointer says "thinking…", then the answer, flying first to what the
answer is about when it starts with a `[POINT:…]` tag. Esc dismisses the answer and the pointer
comes back to the mouse. A new question replaces one still being answered (its answer is dropped).

The desktop is reached only through `AskHost` and `PointerSurface`, so the tests run it with fakes.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .ask import Conversation, Screenshot
from .pointing import parse_pointing, screenshot_point_to_screen

THINKING_CAPTION = "thinking…"
# The ask box is hidden before the screenshot is taken, or the model would see the question box.
COMPOSER_HIDE_SETTLE_SECONDS = 0.15


class PointerSurface(Protocol):
    def show_caption(self, text: str, hold_seconds: float | None) -> None: ...
    def dismiss_caption(self) -> None: ...
    def fly_to(self, screen_x: int, screen_y: int) -> None: ...
    def return_to_mouse(self) -> None: ...


@dataclass
class AskHost:
    show_composer: Callable[[], None]
    hide_composer: Callable[[], None]
    capture_screen: Callable[[], Screenshot]
    screen_size: Callable[[], tuple[int, int]]
    # (question, screenshot, conversation) → the model's answer; raises with a sentence to show.
    ask: Callable[[str, Screenshot, Conversation], str]
    run_in_background: Callable[[Callable[[], Any], Callable[[Any], None]], None]
    schedule: Callable[[float, Callable[[], None]], None]


def caption_hold_seconds(text: str) -> float:
    """Long enough to read: four seconds plus a little per character, at most fifteen."""
    return min(15.0, 4.0 + len(text) * 0.05)


class AskController:
    def __init__(self, host: AskHost, pointer: PointerSurface) -> None:
        self.host = host
        self.pointer = pointer
        self.conversation = Conversation()
        self._question_ids = itertools.count(1)
        self.question_id = 0
        self.is_answering = False
        self.is_showing_answer = False

    def open_composer(self) -> None:
        self.host.show_composer()

    def submit(self, question: str) -> None:
        question = question.strip()
        self.host.hide_composer()
        if not question:
            return
        this_question_id = next(self._question_ids)
        self.question_id = this_question_id
        self.is_answering = True
        self.pointer.show_caption(THINKING_CAPTION, hold_seconds=None)
        self.host.schedule(COMPOSER_HIDE_SETTLE_SECONDS, lambda: self._capture_and_ask(question, this_question_id))

    def _capture_and_ask(self, question: str, this_question_id: int) -> None:
        if this_question_id != self.question_id:
            return
        try:
            screenshot = self.host.capture_screen()
        except Exception as failure:  # noqa: BLE001 - shown to the person, like any other failure
            self._show_failure(f"couldn't see the screen: {failure}", this_question_id)
            return
        conversation = self.conversation
        self.host.run_in_background(
            lambda: (screenshot, self.host.ask(question, screenshot, conversation)),
            lambda outcome: self._show_answer(question, outcome, this_question_id))

    def _show_answer(self, question: str, outcome: Any, this_question_id: int) -> None:
        if this_question_id != self.question_id:
            return
        if isinstance(outcome, BaseException):
            self._show_failure(str(outcome) or "couldn't get an answer", this_question_id)
            return
        screenshot, answer = outcome
        self.is_answering = False
        result = parse_pointing(answer)
        self.conversation.remember(question, answer)
        if result.has_point:
            screen_width, screen_height = self.host.screen_size()
            screen_x, screen_y = screenshot_point_to_screen(result.x, result.y, screenshot.scale, screen_width, screen_height)
            self.pointer.fly_to(screen_x, screen_y)
        text = result.text or "…"
        self.is_showing_answer = True
        self.pointer.show_caption(text, hold_seconds=caption_hold_seconds(text))

    def _show_failure(self, message: str, this_question_id: int) -> None:
        if this_question_id != self.question_id:
            return
        self.is_answering = False
        self.is_showing_answer = True
        self.pointer.show_caption(message, hold_seconds=6.0)

    def escape(self) -> bool:
        """Esc: drops a question still being answered and dismisses the answer. True if it did anything."""
        if not self.is_answering and not self.is_showing_answer:
            return False
        self.question_id = next(self._question_ids)
        self.is_answering = False
        self.is_showing_answer = False
        self.pointer.dismiss_caption()
        self.pointer.return_to_mouse()
        return True

    def caption_finished(self) -> None:
        """The pointer's caption ran out its time: the pointer goes back to the mouse."""
        self.is_showing_answer = False
        self.pointer.return_to_mouse()
