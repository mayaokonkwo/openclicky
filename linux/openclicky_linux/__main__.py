"""`python -m openclicky_linux`: hold the dictation key (right ctrl by default), speak, let go.

`--check` prints what would be used (X server, key, recorder, transcription route) and exits.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from typing import Any, Callable

from .config import load_settings
from .controller import DictationHost, DictationTakeController, OrbModel
from .gestures import DictationGestureRecognizer
from .recorder import MicrophoneRecording, RecorderUnavailable, find_recorder_command
from .space import load_space
from .transcriber import TranscriptionError, route_for, transcribe
from .x11 import is_wayland_session


def _describe_setup(dictation_key: str) -> int:
    settings = load_settings()
    problems = 0
    print(f"dictation key: {dictation_key}")
    try:
        print(f"recorder: {' '.join(find_recorder_command())}")
    except RecorderUnavailable as missing:
        print(f"recorder: missing ({missing})")
        problems += 1
    try:
        route = route_for(b"", settings)
        print(f"transcription: {'your openai key' if route.kind == 'openai' else 'openclicky account at ' + settings.backend_url}")
    except TranscriptionError as missing:
        print(f"transcription: missing ({missing})")
        problems += 1
    print(f"language: {settings.language_code or 'not set (the engine detects it)'}")
    space = load_space()
    print(f"dictionary terms: {len(space.dictionary)}, spoken shortcuts: {len(space.shortcuts)}")
    return 1 if problems else 0


def wire_up(dictation_key: str, start_recording: Callable[[], Any], transcribe: Callable[[bytes], str],
            display_name: str | None = None):
    """The app's parts joined together on the GTK main loop: orb, paste, controller, key listener
    (not started). The X11 tests run exactly this with a stand-in microphone and engine."""
    # `desktop` first: it pins GTK 3 before anything imports it.
    from .desktop import ClipboardPaster, OrbWindow
    from .x11 import DictationKeyListener, focused_window

    from gi.repository import GLib
    from Xlib import display as xdisplay

    xlib_display = xdisplay.Display(display_name)
    orb = OrbModel()
    # Kept alive by the orb, which holds its update method.
    OrbWindow(orb)
    recognizer = DictationGestureRecognizer()
    listener_holder: dict[str, DictationKeyListener] = {}
    paster = ClipboardPaster(xlib_display, before_keystroke=lambda: listener_holder["listener"].ignore_keys_for(0.4))

    def run_in_background(work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        def run() -> None:
            try:
                outcome = work()
            except Exception as failure:  # noqa: BLE001 - handed to the controller, which shows it
                outcome = failure
            GLib.idle_add(lambda: (done(outcome), False)[1])
        threading.Thread(target=run, daemon=True).start()

    def schedule(seconds: float, action: Callable[[], None]) -> None:
        GLib.timeout_add(int(seconds * 1000), lambda: (action(), False)[1])

    controller = DictationTakeController(DictationHost(
        start_recording=start_recording,
        transcribe=transcribe,
        focused_window=lambda: focused_window(xlib_display),
        paste=paster.paste,
        copy_to_clipboard=paster.copy_to_clipboard,
        load_space=load_space,
        run_in_background=run_in_background,
        schedule=schedule,
    ), orb)

    def deliver(events: list) -> None:
        for event in events:
            GLib.idle_add(lambda event=event: (controller.handle(event), False)[1])

    listener = DictationKeyListener(
        dictation_key,
        on_dictation_key=lambda is_down, at_seconds: deliver(
            recognizer.dictation_key_down(at_seconds) if is_down else recognizer.dictation_key_up(at_seconds)),
        on_other_key_down=lambda is_escape: deliver(recognizer.other_key_down(is_escape)),
        display_name=display_name,
    )
    listener_holder["listener"] = listener
    return controller, listener


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openclicky-linux", description="Dictation for Linux: hold a key, speak, let go.")
    parser.add_argument("--key", help="X keysym of the dictation key (default: linuxDictationKey in shell.json, else Control_R)")
    parser.add_argument("--check", action="store_true", help="print the setup and exit")
    arguments = parser.parse_args(argv)

    if is_wayland_session():
        print("openclicky for linux needs an X11 session for now: wayland does not let an app watch a key, "
              "paste into another app or float a window over it. pick the X11 (Xorg) session at login.", file=sys.stderr)
        return 2

    settings = load_settings()
    dictation_key = arguments.key or settings.dictation_key
    if arguments.check:
        return _describe_setup(dictation_key)

    controller, listener = wire_up(dictation_key, start_recording=MicrophoneRecording,
                                   transcribe=lambda wav_bytes: transcribe(wav_bytes, load_settings()))
    # Imported here (after `wire_up` pinned GTK 3) so --check and the wayland message need no display.
    from gi.repository import GLib, Gtk

    listener.start()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (Gtk.main_quit(), False)[1])
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (Gtk.main_quit(), False)[1])
    print(f"openclicky: hold {dictation_key} and speak; let go to type it. tap it to start and tap again to finish; "
          "tap twice or press esc to cancel. ctrl+c quits.")
    try:
        Gtk.main()
    finally:
        listener.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
