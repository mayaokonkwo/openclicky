# OpenClicky for Linux (early)

- **Dictate:** hold **right ctrl**, speak, let go: your words are typed where your cursor is,
  cleaned up the way the Mac app cleans them (fillers out, your dictionary, spoken shortcuts,
  sentence case). A small orb at the bottom of the screen shows each step.
- **Ask:** tap **left ctrl twice**, type a question about what is on your screen, press Enter. The
  orange pointer beside your mouse answers in a caption and flies to what it is talking about.
  Esc dismisses the answer. Follow-ups remember the last ten exchanges.
- **Settings and the tray icon:** Ask…, Settings…, Quit.

Not on Linux yet: spoken answers, asking by voice, the agent lane.

## Needs

- **An X11 session.** Wayland does not let an app watch a key, paste into another app or float a
  window over it; pick the "Xorg" session at login. (On Wayland it says so and exits.)
- Python 3.10+, GTK 3 bindings and a recorder, from your distribution (no cairo bridge needed):
  - Debian/Ubuntu: `sudo apt install python3-gi gir1.2-gtk-3.0 pulseaudio-utils` (or `alsa-utils`)
  - Fedora: `sudo dnf install python3-gobject gtk3 pulseaudio-utils`
- Keys or an account, set in **Settings** (tray icon, or `openclicky-linux settings`). They are
  saved in `~/.openclicky/shell.json`, the file the Mac app and the CLI read, and every other key in
  it is left alone:
  - dictation: an **OpenAI key**, or an **OpenClicky account** token
  - answers: an **Anthropic key**, else the OpenAI key, else the account

  An own key goes straight to its vendor and never to the backend. The language pins dictation and
  answers; the dictation key can be right ctrl, right alt, right super or the menu key (a modifier
  is best, since other keys auto-repeat); the pointer can stay beside the mouse or show only while
  answering.

## Run

```bash
cd linux
python3 -m venv --system-site-packages .venv     # system site packages: GTK comes from the distro
.venv/bin/pip install -e '.[test]'
.venv/bin/openclicky-linux --check               # what it found: key, recorder, transcription route
.venv/bin/openclicky-linux
```

| Do | Get |
|---|---|
| Hold right ctrl, speak, let go | The words are pasted into the window in front |
| Tap right ctrl, speak, tap again | The same, hands off the key |
| Tap right ctrl twice, or esc | Cancel |
| Right ctrl + another key (a shortcut) | Not a take; nothing is typed |
| Tap left ctrl twice | The ask box (Enter sends, esc closes) |
| Esc while an answer shows | Dismiss it; the pointer comes back to the mouse |

The words go only into the window that was in front when you pressed the key: if another window is
in front by the time they are ready, they are put on the clipboard instead ("copied, press ctrl+v").
Terminals get ctrl+shift+v. Your clipboard text is put back 0.6 s after the paste.

Your dictionary and spoken shortcuts are read from `~/.openclicky/dictation/` (the Mac app's files;
edit them there, or by hand).

## Tests

```bash
.venv/bin/python -m pytest
```

The X11 tests start their own Xvfb display (install `xvfb`), so no keystroke reaches your desktop;
they are skipped without it. They run the real app wiring end to end with XTEST pressing keys: a
take lands in a GTK text box; left ctrl twice opens the ask box, a typed question goes out with a
real screenshot to a stand-in model, and the pointer lands on the button it named; Settings saves
into shell.json; the pointer is checked to be cut to its triangle and click-through.
`OPENCLICKY_SCREENSHOT_DIR=<folder>` keeps screenshots of each scenario.

## How it is put together

| File | Purpose |
|---|---|
| `companion.py` | Asking by text, one question at a time: the ask box, the screenshot, the answer, the pointer's flight and caption; a new question or esc drops an unanswered one. Reaches the desktop only through `AskHost` and `PointerSurface`. |
| `ask.py` | The question + screenshot to a model: own Anthropic key → Messages; own OpenAI key → chat completions; account → backend `POST /chat`. The Mac's ask prompt, for a read (not spoken) answer. |
| `pointing.py` | The `[POINT:x,y:label]` tag (the Mac's parser, ported), screenshot → screen coordinates, the arc and timing of a flight. |
| `pointer_view.py` | The pointer (an orange window cut to a triangle with SHAPE, click-through) and its typed-out caption; follows the mouse, flies, comes back. |
| `windows.py` | The ask box, the Settings window, the tray icon. |
| `screen.py` | The screenshot (whole screen, longest side ≤ 1568 px, PNG, with its scale). |
| `controller.py` | One take at a time (idle → listening → finishing), the Mac's `DictationTakeController` in small. Reaches the desktop only through `DictationHost`. |
| `gestures.py` | Hold, tap, double tap, esc and "a shortcut, not a take" from raw key downs and ups, with the Mac's timings. |
| `x11.py` | The window in front (`_NET_ACTIVE_WINDOW`, `WM_CLASS`), the paste keystroke (XTEST), the listen-only key watcher (RECORD), window shapes (SHAPE). |
| `desktop.py` | GTK 3: the clipboard paste and restore, the orb (a popup window that never takes the focus). |
| `recorder.py` | 16 kHz mono PCM from `parecord` or `arecord`, wrapped as WAV. |
| `transcriber.py` | Own OpenAI key → OpenAI; else account → `POST /agent/transcribe`; else a sentence naming what is missing. |
| `formatter.py` | The Mac's `TakeFormatter.formatLocally`, ported: shortcuts, fillers, dictionary, sentence case. |
| `config.py`, `space.py` | `~/.openclicky/shell.json` (read, and saved without touching other keys, mode 600) and the dictionary/shortcut files. |

Not yet: spoken answers and asking by voice, guided steps, more than one screen (the whole X screen
is one image), spoken numbers as digits, the model clean-up, history, the "is there a text box?"
check (AT-SPI), offline engines (Parakeet runs on Linux through sherpa-onnx), Wayland.
