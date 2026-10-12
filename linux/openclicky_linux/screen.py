"""The screenshot a question carries: the whole X screen, scaled down so the longest side is at most
1568 px (what the vision models read at full detail), as PNG. The scale is kept, so a point the
model gives in the screenshot's pixels maps back to the screen's.
"""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf  # noqa: E402

from .ask import Screenshot  # noqa: E402

MAX_SCREENSHOT_SIDE = 1568


def screen_size() -> tuple[int, int]:
    root = Gdk.get_default_root_window()
    return root.get_width(), root.get_height()


def capture_screen() -> Screenshot:
    root = Gdk.get_default_root_window()
    width, height = root.get_width(), root.get_height()
    pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, width, height)
    if pixbuf is None:
        raise RuntimeError("the screen could not be read")
    scale = min(1.0, MAX_SCREENSHOT_SIDE / max(width, height))
    if scale < 1.0:
        pixbuf = pixbuf.scale_simple(round(width * scale), round(height * scale), GdkPixbuf.InterpType.BILINEAR)
    succeeded, png_bytes = pixbuf.save_to_bufferv("png", [], [])
    if not succeeded:
        raise RuntimeError("the screenshot could not be encoded")
    return Screenshot(png_bytes=bytes(png_bytes), width=pixbuf.get_width(), height=pixbuf.get_height(), scale=scale)
