"""Start OpenClicky when you log in: the freedesktop autostart entry every desktop reads
(Xfce, KDE, GNOME, MATE, Cinnamon), `$XDG_CONFIG_HOME/autostart/openclicky.desktop`. Settings
switches it on and off; nothing else writes there.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

DESKTOP_FILE_NAME = "openclicky.desktop"


def autostart_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config_home / "autostart" / DESKTOP_FILE_NAME


def launch_command() -> str:
    """How this copy of OpenClicky starts: its own `openclicky-linux` beside the Python running it
    (a virtualenv's bin), else the one on PATH, else this Python with `-m`."""
    beside_python = Path(sys.executable).with_name("openclicky-linux")
    if beside_python.exists():
        return shlex.quote(str(beside_python))
    on_path = shutil.which("openclicky-linux")
    if on_path:
        return shlex.quote(on_path)
    return f"{shlex.quote(sys.executable)} -m openclicky_linux"


def desktop_entry(command: str) -> str:
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=OpenClicky",
        "Comment=Dictation and a pointer that answers questions about your screen",
        f"Exec={command}",
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
        "",
    ])


def is_enabled() -> bool:
    return autostart_path().exists()


def set_enabled(enabled: bool) -> None:
    path = autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desktop_entry(launch_command()), encoding="utf-8")
    elif path.exists():
        path.unlink()
