"""The ask controller with a fake pointer and desktop: timers and background work run when the test says."""

from openclicky_linux.ask import AskError, Screenshot
from openclicky_linux.companion import THINKING_CAPTION, AskController, AskHost


class FakePointer:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def show_caption(self, text, hold_seconds):
        self.calls.append(("caption", text, hold_seconds is not None))

    def dismiss_caption(self):
        self.calls.append(("dismiss",))

    def fly_to(self, screen_x, screen_y):
        self.calls.append(("fly", screen_x, screen_y))

    def return_to_mouse(self):
        self.calls.append(("home",))


class FakeDesktop:
    def __init__(self) -> None:
        self.composer_open = False
        self.answer: object = "[POINT:none] hello"
        self.asked: list[str] = []
        self.timers: list = []
        self.background: list = []
        self.screenshot = Screenshot(b"png", 784, 490, 0.5)

    def ask(self, question, screenshot, conversation):
        self.asked.append(question)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def host(self) -> AskHost:
        return AskHost(
            show_composer=lambda: setattr(self, "composer_open", True),
            hide_composer=lambda: setattr(self, "composer_open", False),
            capture_screen=lambda: self.screenshot,
            screen_size=lambda: (1568, 980),
            ask=self.ask,
            run_in_background=lambda work, done: self.background.append((work, done)),
            schedule=lambda seconds, action: self.timers.append(action),
        )

    def run_everything(self) -> None:
        while self.timers or self.background:
            while self.timers:
                self.timers.pop(0)()
            while self.background:
                work, done = self.background.pop(0)
                try:
                    outcome = work()
                except Exception as failure:  # noqa: BLE001
                    outcome = failure
                done(outcome)


def make():
    desktop, pointer = FakeDesktop(), FakePointer()
    return desktop, pointer, AskController(desktop.host(), pointer)


def test_a_question_shows_thinking_then_flies_to_the_point_and_shows_the_answer():
    desktop, pointer, asking = make()
    desktop.answer = "[POINT:392,245:save button] click save, top left."
    asking.open_composer()
    assert desktop.composer_open
    asking.submit("  where do i save?  ")
    assert not desktop.composer_open
    assert pointer.calls == [("caption", THINKING_CAPTION, False)]
    desktop.run_everything()
    assert desktop.asked == ["where do i save?"]
    # The screenshot was half size: the point doubles on the screen.
    assert pointer.calls[1:] == [("fly", 784, 490), ("caption", "click save, top left.", True)]
    assert asking.conversation.exchanges == [("where do i save?", "[POINT:392,245:save button] click save, top left.")]


def test_an_answer_without_a_point_stays_by_the_mouse():
    desktop, pointer, asking = make()
    asking.submit("what is html?")
    desktop.run_everything()
    assert ("caption", "hello", True) in pointer.calls
    assert not any(call[0] == "fly" for call in pointer.calls)


def test_an_empty_question_just_closes_the_box():
    desktop, pointer, asking = make()
    asking.open_composer()
    asking.submit("   ")
    assert not desktop.composer_open
    assert pointer.calls == []
    assert desktop.timers == []


def test_a_failure_is_said_by_the_pointer():
    desktop, pointer, asking = make()
    desktop.answer = AskError("asking needs an anthropic or openai key, or an openclicky account. add one in settings.")
    asking.submit("hi")
    desktop.run_everything()
    assert pointer.calls[-1] == ("caption", "asking needs an anthropic or openai key, or an openclicky account. add one in settings.", True)
    assert not asking.is_answering


def test_esc_while_thinking_drops_the_answer():
    desktop, pointer, asking = make()
    desktop.answer = "[POINT:10,10:x] late answer"
    asking.submit("hi")
    assert asking.escape()
    desktop.run_everything()
    assert not any(call[0] == "fly" or call[1:2] == ("late answer",) for call in pointer.calls)
    assert pointer.calls[-2:] == [("dismiss",), ("home",)]


def test_a_new_question_replaces_one_still_being_answered():
    desktop, pointer, asking = make()
    asking.submit("first")
    first_timer = desktop.timers.pop()
    desktop.answer = "[POINT:none] second answer"
    asking.submit("second")
    first_timer()  # the first question's screenshot moment comes late: ignored
    desktop.run_everything()
    assert desktop.asked == ["second"]
    assert pointer.calls[-1] == ("caption", "second answer", True)


def test_esc_with_nothing_showing_does_nothing():
    _desktop, pointer, asking = make()
    assert not asking.escape()
    assert pointer.calls == []


def test_when_the_caption_runs_out_the_pointer_goes_home():
    desktop, pointer, asking = make()
    asking.submit("hi")
    desktop.run_everything()
    asking.caption_finished()
    assert pointer.calls[-1] == ("home",)
    assert not asking.is_showing_answer
