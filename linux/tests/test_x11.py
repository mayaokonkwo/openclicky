"""The X11 parts against a real X server: a private Xvfb started for these tests, so no keystroke
ever reaches the desktop the tests run on. Skipped where Xvfb is not installed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.x11

LINUX_DIRECTORY = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def private_display():
    if not shutil.which("Xvfb"):
        pytest.skip("Xvfb is not installed")
    for number in range(91, 120):
        if not Path(f"/tmp/.X11-unix/X{number}").exists() and not Path(f"/tmp/.X{number}-lock").exists():
            break
    server = subprocess.Popen(["Xvfb", f":{number}", "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while not Path(f"/tmp/.X11-unix/X{number}").exists():
        if time.monotonic() > deadline or server.poll() is not None:
            server.kill()
            pytest.fail("Xvfb did not start")
        time.sleep(0.05)
    yield f":{number}"
    server.terminate()
    server.wait(timeout=5)


def run_scenario(name: str, display: str) -> dict:
    environment = {key: value for key, value in os.environ.items() if key not in ("WAYLAND_DISPLAY", "XAUTHORITY")}
    environment.update(DISPLAY=display, PYTHONPATH=str(LINUX_DIRECTORY), GDK_BACKEND="x11", NO_AT_BRIDGE="1",
                       OPENCLICKY_HOME=str(LINUX_DIRECTORY / "tests" / "no-such-openclicky-home"))
    finished = subprocess.run([sys.executable, str(LINUX_DIRECTORY / "tests" / "x11_scenarios.py"), name],
                              env=environment, capture_output=True, text=True, timeout=60)
    assert finished.returncode == 0, finished.stderr
    return json.loads(finished.stdout.strip().splitlines()[-1])


def test_the_listener_sees_the_dictation_key_other_keys_and_escape_but_not_our_own_keystrokes(private_display):
    seen = run_scenario("key_listener", private_display)["seen"]
    assert seen == [["dictation", True], ["other", False], ["dictation", False], ["other", True]]


def test_the_window_in_front_and_whether_it_is_a_terminal(private_display):
    assert run_scenario("focused_window", private_display) == {"app_class": "xterm", "is_terminal": True}


def test_holding_the_key_types_the_words_into_the_text_box_and_puts_the_clipboard_back(private_display):
    outcome = run_scenario("dictate_into_text_box", private_display)
    # No dictionary in this test's OpenClicky home: fillers out, sentence case, nothing else.
    assert outcome["text_box"] == "Hello from open clicky"
    assert outcome["clipboard"] == "what was on the clipboard before"
    assert ["done", "moved to text box"] in outcome["orb_history"]


def test_a_key_typed_while_holding_cancels_the_take(private_display):
    outcome = run_scenario("key_used_as_shortcut", private_display)
    assert outcome["text_box"] == ""
    assert ["failed", "cancelled, that was a shortcut"] in outcome["orb_history"]
    assert not any(phase == "done" for phase, _ in outcome["orb_history"])
