"""Scenarios run against a private Xvfb display by `test_x11.py`, one per child process (GTK binds
to a display once per process). Each prints one JSON line with what it saw. Keys are pressed with
XTEST, exactly as a keyboard would: through the X server, seen by the RECORD listener.
"""

from __future__ import annotations

import json
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gdk, GdkX11, Gtk  # noqa: E402,F401
from Xlib import X, XK, display as xdisplay  # noqa: E402
from Xlib.ext import xtest  # noqa: E402

from openclicky_linux.__main__ import wire_up  # noqa: E402
from openclicky_linux.recorder import SAMPLE_RATE  # noqa: E402
from openclicky_linux.x11 import DictationKeyListener, focused_window  # noqa: E402

keyboard = xdisplay.Display()


def pump(seconds: float, until=lambda: False) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not until():
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.01)


def key(keysym_name: str, is_down: bool) -> None:
    keycode = keyboard.keysym_to_keycode(XK.string_to_keysym(keysym_name))
    xtest.fake_input(keyboard, X.KeyPress if is_down else X.KeyRelease, keycode)
    keyboard.sync()


def text_box_window(window_class: str | None = None):
    window = Gtk.Window(title="scenario")
    if window_class:
        window.set_wmclass(window_class, window_class)
    entry = Gtk.Entry()
    window.add(entry)
    window.show_all()
    pump(0.3)
    # No window manager on Xvfb: the focus is given by hand, as a click would.
    xid = window.get_window().get_xid()
    keyboard.set_input_focus(xid, X.RevertToParent, X.CurrentTime)
    keyboard.sync()
    entry.grab_focus()
    pump(0.3)
    return window, entry


class StandInRecording:
    def stop(self) -> bytes:
        return b"\x01\x00" * SAMPLE_RATE

    def cancel(self) -> None:
        pass


def scenario_key_listener() -> dict:
    seen: list = []
    listener = DictationKeyListener("Control_R", on_dictation_key=lambda is_down, _at: seen.append(["dictation", is_down]),
                                    on_other_key_down=lambda is_escape: seen.append(["other", is_escape]))
    listener.start()
    time.sleep(0.3)
    for name, is_down in [("Control_R", True), ("a", True), ("a", False), ("Control_R", False), ("Escape", True), ("Escape", False)]:
        key(name, is_down)
        time.sleep(0.05)
    time.sleep(0.3)
    listener.ignore_keys_for(0.5)
    key("Control_R", True)
    key("Control_R", False)
    time.sleep(0.3)
    listener.stop()
    return {"seen": seen}


def scenario_focused_window() -> dict:
    _window, _entry = text_box_window("xterm")
    found = focused_window(keyboard)
    return {"app_class": found and found.app_class, "is_terminal": found and found.is_terminal}


def _dictate(hold_seconds: float, keys_during_hold: tuple[str, ...] = ()) -> dict:
    _window, entry = text_box_window()
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text("what was on the clipboard before", -1)
    pump(0.1)
    app = wire_up("Control_R", start_recording=StandInRecording, transcribe=lambda _wav: "um, hello from open clicky")
    controller, listener = app.dictation, app.listener
    orb_history: list = []
    controller.orb.listeners.append(lambda orb: orb_history.append([orb.phase, orb.message]))
    listener.start()
    pump(0.3)
    key("Control_R", True)
    pump(0.1)
    for name in keys_during_hold:
        key(name, True)
        key(name, False)
    pump(hold_seconds)
    key("Control_R", False)
    pump(5, until=lambda: bool(entry.get_text()) or any(phase == "failed" for phase, _ in orb_history))
    pump(1.0)  # past the clipboard restore
    listener.stop()
    return {"text_box": entry.get_text(), "clipboard": clipboard.wait_for_text(),
            "orb_history": orb_history}


def scenario_dictate_into_text_box() -> dict:
    return _dictate(hold_seconds=0.6)


def scenario_key_used_as_shortcut() -> dict:
    return _dictate(hold_seconds=0.6, keys_during_hold=("c",))



# MARK: the pointer, the ask box, Settings

import os  # noqa: E402

from Xlib.ext import xtest as _xtest  # noqa: E402,F811

SCREENSHOT_DIRECTORY = os.environ.get("OPENCLICKY_SCREENSHOT_DIR")


def screenshot(name: str) -> None:
    if not SCREENSHOT_DIRECTORY:
        return
    pump(0.2)
    root = Gdk.get_default_root_window()
    Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height()).savev(
        os.path.join(SCREENSHOT_DIRECTORY, f"{name}.png"), "png", [], [])


def move_mouse(x: int, y: int) -> None:
    _xtest.fake_input(keyboard, X.MotionNotify, x=x, y=y)
    keyboard.sync()


def tap(keysym_name: str) -> None:
    key(keysym_name, True)
    time.sleep(0.03)
    key(keysym_name, False)


def type_text(text: str) -> None:
    for character in text:
        keysym_name = {" ": "space", "?": "question"}.get(character, character)
        keysym = XK.string_to_keysym(keysym_name)
        # A character on the shifted level of its key ("?" on "/") is typed with shift held.
        needs_shift = keyboard.keycode_to_keysym(keyboard.keysym_to_keycode(keysym), 0) != keysym
        if needs_shift:
            key("Shift_L", True)
        tap(keysym_name)
        if needs_shift:
            key("Shift_L", False)
        time.sleep(0.01)


def app_window_with_a_save_button():
    window = Gtk.Window(title="Notes")
    window.set_default_size(900, 500)
    layout = Gtk.Fixed()
    save = Gtk.Button(label="Save")
    layout.put(save, 640, 380)
    layout.put(Gtk.Label(label="An app the question is about"), 40, 40)
    window.add(layout)
    window.move(150, 120)
    window.show_all()
    pump(0.5)
    allocation = save.get_allocation()
    origin_x, origin_y = window.get_window().get_origin()[1:3]
    return window, (origin_x + allocation.x + allocation.width // 2, origin_y + allocation.y + allocation.height // 2)


def scenario_pointer_follows_the_mouse() -> dict:
    app = wire_up("Control_R", start_recording=StandInRecording, transcribe=lambda _wav: "")
    positions = []
    for x, y in ((300, 300), (700, 420)):
        move_mouse(x, y)
        pump(0.3)
        positions.append([round(value) for value in app.pointer.position] + [list(app.pointer.triangle.get_window().get_position())])
    screenshot("pointer-following")
    from Xlib.ext import shape as x_shape
    triangle = keyboard.create_resource_object("window", app.pointer.triangle.get_window().get_xid())
    return {"positions": positions, "visible": app.pointer.triangle.get_visible(),
            "outline_rows": len(triangle.shape_get_rectangles(x_shape.SK.Bounding).rectangles),
            "clickable_rectangles": len(triangle.shape_get_rectangles(x_shape.SK.Input).rectangles)}


def scenario_ask_and_point() -> dict:
    window, save_center = app_window_with_a_save_button()
    asked = []

    def stand_in_model(question, screenshot_taken, conversation):
        asked.append([question, screenshot_taken.width, screenshot_taken.height, len(screenshot_taken.png_bytes) > 1000])
        time.sleep(0.4)
        return f"[POINT:{save_center[0]},{save_center[1]}:save button] that save button down on the right keeps your note."

    app = wire_up("Control_R", start_recording=StandInRecording, transcribe=lambda _wav: "", ask=stand_in_model)
    app.listener.start()
    move_mouse(260, 260)
    pump(0.4)
    tap("Control_L")
    pump(0.1)
    tap("Control_L")
    pump(2, until=lambda: app.composer.is_open and app.composer.entry.has_focus())
    composer_opened = app.composer.is_open
    composer_has_keyboard = app.composer.entry.has_focus()
    type_text("where do i save this?")
    pump(0.3)
    screenshot("ask-box")
    typed = app.composer.entry.get_text()
    tap("Return")
    pump(0.2)
    thinking = app.pointer.caption_label.get_text()
    pump(6, until=lambda: app.pointer.mode == "pointing" and "keeps your note" in app.pointer.caption_label.get_text())
    pump(0.3)
    screenshot("answer-and-point")
    pointed_at = [round(value) for value in app.pointer.position]
    caption = app.pointer.caption_label.get_text()
    composer_closed = not app.composer.is_open
    tap("Escape")
    pump(3, until=lambda: app.pointer.mode == "following")
    pump(0.2)
    app.listener.stop()
    return {"composer_opened": composer_opened, "composer_has_keyboard": composer_has_keyboard, "typed": typed,
            "composer_closed": composer_closed, "thinking": thinking, "asked": asked, "save_center": list(save_center),
            "pointed_at": pointed_at, "caption": caption, "after_escape": [app.pointer.mode, app.pointer.caption.get_visible()]}


def scenario_settings_window() -> dict:
    app = wire_up("Control_R", start_recording=StandInRecording, transcribe=lambda _wav: "")
    settings = app.settings_window
    settings.show()
    pump(0.5)
    routes_before = settings.routes_label.get_text()
    settings.fields["anthropic_api_key"].set_text("sk-ant-test")
    settings.fields["language_code"].set_text("en-IN")
    settings.fields["dictation_key"].set_active_id("Alt_R")
    settings.fields["pointer_presence"].set_active_id("whenAnswering")
    pump(0.2)
    routes_after = settings.routes_label.get_text()
    screenshot("settings")
    settings.save_button.clicked()
    pump(0.3)
    shell_json = os.path.join(os.environ["OPENCLICKY_HOME"], "shell.json")
    with open(shell_json, encoding="utf-8") as saved_file:
        saved = json.load(saved_file)
    return {"routes_before": routes_before, "routes_after": routes_after, "saved": saved,
            "mode": oct(os.stat(shell_json).st_mode & 0o777), "status": settings.status_label.get_text(),
            "pointer_presence_now": app.pointer.presence, "pointer_visible_while_following": app.pointer.triangle.get_visible()}


def scenario_shake_to_appear() -> dict:
    app = wire_up("Control_R", start_recording=StandInRecording, transcribe=lambda _wav: "")
    app.pointer.set_presence("onShake")
    app.pointer.tracker.rest_delay_seconds = 1.0
    seen = {}
    move_mouse(400, 300)
    pump(0.4)
    seen["at_start"] = app.pointer.triangle.get_visible()
    for x in range(400, 900, 25):  # an ordinary move across the screen
        move_mouse(x, 300)
        pump(0.034)
    seen["after_a_plain_move"] = app.pointer.triangle.get_visible()
    x = 620
    for swing in range(6):  # a shake: quick 160 px swings, side to side, four steps each
        target = 780 if swing % 2 == 0 else 620
        for step in range(1, 5):
            move_mouse(round(x + (target - x) * step / 4), 300)
            pump(0.034)
        x = target
    seen["after_a_shake"] = app.pointer.triangle.get_visible()
    screenshot("shake-to-appear")
    pump(1.6)
    seen["after_resting"] = app.pointer.triangle.get_visible()
    app.pointer.set_presence("whileMoving")
    seen["while_moving_after_rest"] = app.pointer.triangle.get_visible()
    move_mouse(500, 400)
    pump(0.2)
    seen["while_moving_after_a_nudge"] = app.pointer.triangle.get_visible()
    return seen


# MARK: live: a real model through the person's own key (only with OPENCLICKY_LIVE=1)

def editor_window():
    """A small editor-like app: a toolbar of labelled buttons and a text area, at known places."""
    window = Gtk.Window(title="Notes — shopping list")
    window.set_default_size(980, 600)
    layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    toolbar = Gtk.Box(spacing=12)
    buttons = {}
    for label in ("New", "Open", "Save", "Print", "Settings"):
        button = Gtk.Button(label=label)
        toolbar.pack_start(button, False, False, 0)
        buttons[label] = button
    layout.pack_start(toolbar, False, False, 0)
    text = Gtk.TextView()
    text.get_buffer().set_text("milk\neggs\nbread\n")
    layout.pack_start(text, True, True, 0)
    footer = Gtk.Box()
    delete = Gtk.Button(label="Delete note")
    footer.pack_end(delete, False, False, 0)
    buttons["Delete note"] = delete
    layout.pack_start(footer, False, False, 0)
    window.add(layout)
    window.move(120, 90)
    window.show_all()
    pump(0.6)
    origin_x, origin_y = window.get_window().get_origin()[1:3]
    boxes = {}
    for label, button in buttons.items():
        allocation = button.get_allocation()
        boxes[label] = [origin_x + allocation.x, origin_y + allocation.y, allocation.width, allocation.height]
    return window, boxes


def scenario_live_questions() -> dict:
    window, boxes = editor_window()
    app = wire_up("Control_R", start_recording=StandInRecording, transcribe=lambda _wav: "")
    app.listener.start()
    move_mouse(300, 400)
    pump(0.3)
    results = []
    for index, question in enumerate(json.loads(os.environ["OPENCLICKY_LIVE_QUESTIONS"])):
        started = time.monotonic()
        app.asking.submit(question)
        pump(60, until=lambda: not app.asking.is_answering and app.pointer.mode != "flying"
             and app.pointer.caption_label.get_text() not in ("", "thinking…"[:len(app.pointer.caption_label.get_text())]))
        pump(1.5)  # the caption finishes typing
        results.append({"question": question, "seconds": round(time.monotonic() - started, 1),
                        "answer": app.asking.conversation.exchanges[-1][1] if app.asking.conversation.exchanges else None,
                        "caption": app.pointer.caption_label.get_text(), "mode": app.pointer.mode,
                        "pointer": [round(value) for value in app.pointer.position]})
        screenshot(f"live-{index + 1}")
        app.asking.escape()
        pump(1.5, until=lambda: app.pointer.mode == "following")
    app.listener.stop()
    return {"boxes": boxes, "results": results}

if __name__ == "__main__":
    print(json.dumps(globals()[f"scenario_{sys.argv[1]}"]()))
