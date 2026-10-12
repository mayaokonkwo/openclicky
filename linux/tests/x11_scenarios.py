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
    controller, listener = wire_up("Control_R", start_recording=StandInRecording,
                                   transcribe=lambda _wav: "um, hello from open clicky")
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


if __name__ == "__main__":
    print(json.dumps(globals()[f"scenario_{sys.argv[1]}"]()))
