"""X11: the window in front, the paste keystroke, and the dictation key.

- `focused_window` reads `_NET_ACTIVE_WINDOW` (any EWMH window manager) and falls back to the
  input focus when no window manager sets it, then the window's `WM_CLASS`, so terminals get
  ctrl+shift+v instead of ctrl+v.
- `send_paste_keystroke` posts the keystroke with XTEST to whatever has the focus.
- `DictationKeyListener` watches every key press and release through the RECORD extension:
  listen-only, like the Mac app's `CGEvent` tap, so the key keeps working in other apps and
  nothing is grabbed. It runs on its own thread with its own connections.

Wayland deliberately allows none of this; `is_wayland_session` lets the app say so at start.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

from Xlib import X, XK, display as xdisplay
from Xlib.error import XError
from Xlib.ext import record, xtest
from Xlib.protocol import rq

from .controller import FocusedWindow

# WM_CLASS values (lowercased) of terminals, where paste is ctrl+shift+v (ctrl+v is a literal ^V).
TERMINAL_WINDOW_CLASSES = frozenset({
    "gnome-terminal", "gnome-terminal-server", "org.gnome.console", "kgx", "konsole", "xterm", "uxterm",
    "urxvt", "rxvt", "kitty", "alacritty", "tilix", "terminator", "xfce4-terminal", "mate-terminal",
    "lxterminal", "qterminal", "terminology", "wezterm", "wezterm-gui", "foot", "st", "st-256color",
    "guake", "yakuake", "tilda", "cool-retro-term", "sakura", "ptyxis",
})


def is_wayland_session(environment: dict[str, str] | None = None) -> bool:
    environment = os.environ if environment is None else environment
    return environment.get("XDG_SESSION_TYPE") == "wayland" or (
        bool(environment.get("WAYLAND_DISPLAY")) and not environment.get("DISPLAY"))


def _window_class(display: xdisplay.Display, window) -> str | None:
    """WM_CLASS of the window or its nearest ancestor that has one (the input focus is often a child)."""
    current = window
    for _ in range(8):
        try:
            wm_class = current.get_wm_class()
            if wm_class:
                return wm_class[1] or wm_class[0]
            tree = current.query_tree()
        except XError:
            return None
        if not tree.parent or tree.parent == tree.root or tree.parent.id == 0:
            return None
        current = tree.parent
    return None


def focused_window(display: xdisplay.Display) -> FocusedWindow | None:
    root = display.screen().root
    window = None
    try:
        active = root.get_full_property(display.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
        if active and active.value and active.value[0]:
            window = display.create_resource_object("window", int(active.value[0]))
        else:
            focus = display.get_input_focus().focus
            if isinstance(focus, int) or focus is None or focus == root:
                return None
            window = focus
    except XError:
        return None
    app_class = _window_class(display, window)
    is_terminal = bool(app_class) and app_class.lower() in TERMINAL_WINDOW_CLASSES
    return FocusedWindow(window_id=window.id, app_class=app_class, is_terminal=is_terminal)


def send_paste_keystroke(display: xdisplay.Display, with_shift: bool) -> bool:
    """ctrl+v (ctrl+shift+v in a terminal) to the focused window. False without XTEST."""
    if not display.has_extension("XTEST"):
        return False
    keycodes = [display.keysym_to_keycode(XK.XK_Control_L)]
    if with_shift:
        keycodes.append(display.keysym_to_keycode(XK.XK_Shift_L))
    keycodes.append(display.keysym_to_keycode(XK.XK_v))
    if not all(keycodes):
        return False
    for keycode in keycodes:
        xtest.fake_input(display, X.KeyPress, keycode)
    for keycode in reversed(keycodes):
        xtest.fake_input(display, X.KeyRelease, keycode)
    display.sync()
    return True


class DictationKeyListener:
    """Calls `on_dictation_key(is_down, at_seconds)` and `on_other_key_down(is_escape)` from its own
    thread for every key press and release on the X server."""

    def __init__(self, dictation_key_name: str, on_dictation_key: Callable[[bool, float], None],
                 on_other_key_down: Callable[[bool], None], display_name: str | None = None) -> None:
        self._control_display = xdisplay.Display(display_name)
        self._record_display = xdisplay.Display(display_name)
        if not self._record_display.has_extension("RECORD"):
            raise RuntimeError("the X server has no RECORD extension, so the dictation key cannot be watched")
        dictation_keysym = XK.string_to_keysym(dictation_key_name)
        if dictation_keysym == X.NoSymbol:
            raise ValueError(f"unknown key name {dictation_key_name!r} (an X keysym such as Control_R, Alt_R, Super_R)")
        self.dictation_keycodes = self._keycodes_for(dictation_keysym)
        if not self.dictation_keycodes:
            raise ValueError(f"no key on this keyboard produces {dictation_key_name}")
        self.escape_keycodes = self._keycodes_for(XK.XK_Escape)
        self._on_dictation_key = on_dictation_key
        self._on_other_key_down = on_other_key_down
        # Our own XTEST keystrokes (the paste) are seen too; they are ignored until this time.
        self._ignore_until = 0.0
        self._context = None
        self._thread: threading.Thread | None = None

    def _keycodes_for(self, keysym: int) -> set[int]:
        return {keycode for keycode, _index in self._control_display.keysym_to_keycodes(keysym)}

    def ignore_keys_for(self, seconds: float) -> None:
        self._ignore_until = time.monotonic() + seconds

    def start(self) -> None:
        self._context = self._record_display.record_create_context(0, [record.AllClients], [{
            "core_requests": (0, 0), "core_replies": (0, 0),
            "ext_requests": (0, 0, 0, 0), "ext_replies": (0, 0, 0, 0),
            "delivered_events": (0, 0), "device_events": (X.KeyPress, X.KeyRelease),
            "errors": (0, 0), "client_started": False, "client_died": False,
        }])
        self._thread = threading.Thread(target=self._record_display.record_enable_context,
                                        args=(self._context, self._handle_reply), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._context is None:
            return
        self._control_display.record_disable_context(self._context)
        self._control_display.flush()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._record_display.record_free_context(self._context)
        self._context = None

    def _handle_reply(self, reply) -> None:
        if reply.category != record.FromServer or reply.client_swapped or not reply.data:
            return
        data = reply.data
        while data:
            event, data = rq.EventField(None).parse_binary_value(data, self._record_display.display, None, None)
            if event.type not in (X.KeyPress, X.KeyRelease) or time.monotonic() < self._ignore_until:
                continue
            is_down = event.type == X.KeyPress
            if event.detail in self.dictation_keycodes:
                self._on_dictation_key(is_down, event.time / 1000.0)
            elif is_down:
                self._on_other_key_down(event.detail in self.escape_keycodes)
