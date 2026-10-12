"""The windows people use directly: the ask box, the Settings window, and the tray icon.

- The ask box (left ctrl tapped twice, or the tray): one line, Enter sends, Esc closes. It takes the
  keyboard while open; when it closes the window manager gives the focus back.
- Settings: the fields in `~/.openclicky/shell.json` that matter on Linux, in groups (dictation, the
  pointer, keys & account), with a line that says where dictation and answers will go as you type.
  Save writes them with `config.save_settings` (every other key stays). Keys show as dots.
- The tray icon (any system tray: Xfce, KDE, MATE, Cinnamon; GNOME needs an extension): Ask…,
  Settings…, Quit.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gdk, GdkPixbuf, GdkX11, GLib, Gtk  # noqa: E402

from .config import HOSTED_BACKEND_URL, LinuxSettings, load_settings, save_settings  # noqa: E402
from .presence import PRESENCE_LABELS  # noqa: E402
from .pointer_view import POINTER_OUTLINE, POINTER_HEIGHT, POINTER_WIDTH  # noqa: E402
from .x11 import polygon_rows  # noqa: E402

DICTATION_KEY_CHOICES = (("Control_R", "right ctrl"), ("Alt_R", "right alt"), ("Super_R", "right super"), ("Menu", "menu key"))
POINTER_CHOICES = tuple(PRESENCE_LABELS.items())


def present_with_focus(window: Gtk.Window) -> None:
    """Shows the window and asks for the keyboard with the X server's own time: opened from a key
    watched through RECORD there is no GTK event, and without a time window managers refuse focus."""
    window.show_all()
    gdk_window = window.get_window()
    timestamp = GdkX11.x11_get_server_time(gdk_window) if isinstance(gdk_window, GdkX11.X11Window) else Gdk.CURRENT_TIME
    window.present_with_time(timestamp)


class ComposerWindow:
    WIDTH = 520
    TOP_MARGIN = 120

    def __init__(self, on_submit: Callable[[str], None]) -> None:
        self.window = Gtk.Window(title="Ask OpenClicky")
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.window.set_default_size(self.WIDTH, -1)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("ask about your screen…  (enter sends, esc closes)")
        self.entry.set_margin_start(10)
        self.entry.set_margin_end(10)
        self.entry.set_margin_top(10)
        self.entry.set_margin_bottom(10)
        self.window.add(self.entry)
        self.entry.connect("activate", lambda entry: on_submit(entry.get_text()))
        self.window.connect("key-press-event", self._on_key)
        self.window.connect("delete-event", lambda *_: self.hide() or True)

    def _on_key(self, _window, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def show(self) -> None:
        self.entry.set_text("")
        screen_width = Gdk.get_default_root_window().get_width()
        self.window.move((screen_width - self.WIDTH) // 2, self.TOP_MARGIN)
        present_with_focus(self.window)
        self.entry.grab_focus()

    def hide(self) -> None:
        self.window.hide()

    @property
    def is_open(self) -> bool:
        return self.window.get_visible()


class SettingsWindow:
    def __init__(self, on_saved: Callable[[LinuxSettings], None] = lambda _settings: None) -> None:
        self.on_saved = on_saved
        self.window = Gtk.Window(title="OpenClicky Settings")
        self.window.set_default_size(560, -1)
        self.window.set_border_width(18)
        self.window.connect("delete-event", lambda *_: self.window.hide() or True)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.window.add(layout)
        self.fields: dict[str, Gtk.Widget] = {}

        self._heading(layout, "Dictation")
        self.fields["dictation_key"] = self._choice(layout, "Hold to dictate", DICTATION_KEY_CHOICES)
        self.fields["language_code"] = self._text(layout, "Language", "blank: the engine detects it (en, hi-IN, ta…)")
        self._heading(layout, "Pointer")
        self.fields["pointer_presence"] = self._choice(layout, "Show the pointer", POINTER_CHOICES)
        self._heading(layout, "Keys & account")
        self.fields["openai_api_key"] = self._text(layout, "OpenAI key", "sk-… (dictation, and answers without an Anthropic key)", secret=True)
        self.fields["anthropic_api_key"] = self._text(layout, "Anthropic key", "sk-ant-… (answers)", secret=True)
        self.fields["openrouter_api_key"] = self._text(layout, "OpenRouter key", "sk-or-… (answers, when there is no Anthropic key)", secret=True)
        self.fields["account_token"] = self._text(layout, "OpenClicky token", "an account token, used when a key is missing", secret=True)
        self.fields["backend_url"] = self._text(layout, "Backend", HOSTED_BACKEND_URL)

        self.routes_label = Gtk.Label(xalign=0)
        self.routes_label.set_line_wrap(True)
        self.routes_label.set_margin_top(12)
        layout.pack_start(self.routes_label, False, False, 0)
        self.status_label = Gtk.Label(xalign=0)
        layout.pack_start(self.status_label, False, False, 0)

        buttons = Gtk.Box(spacing=8)
        buttons.set_halign(Gtk.Align.END)
        buttons.set_margin_top(12)
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _button: self.window.hide())
        self.save_button = Gtk.Button(label="Save")
        self.save_button.get_style_context().add_class("suggested-action")
        self.save_button.connect("clicked", lambda _button: self.save())
        buttons.pack_start(close_button, False, False, 0)
        buttons.pack_start(self.save_button, False, False, 0)
        layout.pack_start(buttons, False, False, 0)
        for widget in self.fields.values():
            widget.connect("changed", lambda _widget: self._update_routes())

    # MARK: building

    def _heading(self, layout: Gtk.Box, title: str) -> None:
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        label.set_margin_top(10)
        layout.pack_start(label, False, False, 0)

    def _row(self, layout: Gtk.Box, title: str, widget: Gtk.Widget) -> None:
        row = Gtk.Box(spacing=12)
        label = Gtk.Label(label=title, xalign=0)
        label.set_size_request(150, -1)
        row.pack_start(label, False, False, 0)
        row.pack_start(widget, True, True, 0)
        layout.pack_start(row, False, False, 0)

    def _text(self, layout: Gtk.Box, title: str, placeholder: str, secret: bool = False) -> Gtk.Entry:
        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        entry.set_visibility(not secret)
        self._row(layout, title, entry)
        return entry

    def _choice(self, layout: Gtk.Box, title: str, choices: tuple[tuple[str, str], ...]) -> Gtk.ComboBoxText:
        combo = Gtk.ComboBoxText()
        for value, label in choices:
            combo.append(value, label)
        self._row(layout, title, combo)
        return combo

    # MARK: values

    def load(self) -> None:
        settings = load_settings()
        for field_name, widget in self.fields.items():
            value = getattr(settings, field_name)
            if isinstance(widget, Gtk.ComboBoxText):
                if not widget.set_active_id(value):
                    # A key picked by hand in shell.json that is not in the list is shown, not lost.
                    widget.append(value, value)
                    widget.set_active_id(value)
            elif field_name == "backend_url":
                widget.set_text("" if value == HOSTED_BACKEND_URL else value)
            else:
                widget.set_text(value or "")
        self.status_label.set_text("")
        self._update_routes()

    def values(self) -> dict[str, str | None]:
        return {field_name: (widget.get_active_id() if isinstance(widget, Gtk.ComboBoxText) else widget.get_text())
                for field_name, widget in self.fields.items()}

    def _update_routes(self) -> None:
        values = self.values()
        def has(field_name: str) -> bool:
            return bool((values.get(field_name) or "").strip())
        dictation = "your OpenAI key" if has("openai_api_key") else "your OpenClicky account" if has("account_token") else "nothing yet: add an OpenAI key or a token"
        answers = ("your Anthropic key" if has("anthropic_api_key") else "your OpenRouter key" if has("openrouter_api_key")
                   else "your OpenAI key" if has("openai_api_key")
                   else "your OpenClicky account" if has("account_token") else "nothing yet: add a key or a token")
        self.routes_label.set_text(f"Dictation goes to {dictation}.\nAnswers come from {answers}.")

    def save(self) -> None:
        try:
            save_settings(self.values())
        except (OSError, ValueError) as failure:
            self.status_label.set_text(f"Not saved: {failure}")
            return
        self.status_label.set_text("Saved. A new dictation key takes effect when OpenClicky restarts.")
        self.on_saved(load_settings())

    def show(self) -> None:
        self.load()
        present_with_focus(self.window)


def pointer_icon(size: int = 22) -> GdkPixbuf.Pixbuf:
    """The tray icon: the pointer's own triangle, drawn pixel by pixel (no cairo bridge needed)."""
    scale = (size - 4) / max(POINTER_WIDTH, POINTER_HEIGHT)
    outline = [(3 + x * scale, 2 + y * scale) for x, y in POINTER_OUTLINE]
    pixels = bytearray(size * size * 4)
    for x, y, width, _height in polygon_rows(outline, size, size):
        for column in range(x, x + width):
            offset = (y * size + column) * 4
            pixels[offset:offset + 4] = bytes((0xF0, 0x45, 0x2B, 0xFF))
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(pixels)), GdkPixbuf.Colorspace.RGB, True, 8, size, size, size * 4)


class TrayIcon:
    def __init__(self, on_ask: Callable[[], None], on_settings: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self.menu = Gtk.Menu()
        for label, action in (("Ask…", on_ask), ("Settings…", on_settings), (None, None), ("Quit", on_quit)):
            item = Gtk.SeparatorMenuItem() if label is None else Gtk.MenuItem(label=label)
            if action is not None:
                item.connect("activate", lambda _item, action=action: action())
            self.menu.append(item)
        self.menu.show_all()
        # Gtk.StatusIcon is the X11 system tray protocol: deprecated in GTK, still what Xfce, KDE,
        # MATE and Cinnamon trays show. Where there is no tray, the shortcuts still work.
        self.icon = Gtk.StatusIcon.new_from_pixbuf(pointer_icon())
        self.icon.set_tooltip_text("OpenClicky")
        self.icon.connect("activate", lambda _icon: on_ask())
        self.icon.connect("popup-menu", lambda icon, button, time: self.menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time))
