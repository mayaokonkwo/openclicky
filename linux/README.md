# OpenClicky for Linux (dictation, early)

Hold **right ctrl**, speak, let go: your words are typed where your cursor is, cleaned up the way
the Mac app cleans them (fillers out, your dictionary, spoken shortcuts, sentence case). A small orb
at the bottom of the screen shows each step.

This is the first piece of a Linux client: dictation only. The pointer, asking about your screen,
and the agent lane are Mac-only for now.

## Needs

- **An X11 session.** Wayland does not let an app watch a key, paste into another app or float a
  window over it; pick the "Xorg" session at login. (On Wayland it says so and exits.)
- Python 3.10+, GTK 3 bindings and a recorder, from your distribution:
  - Debian/Ubuntu: `sudo apt install python3-gi gir1.2-gtk-3.0 pulseaudio-utils` (or `alsa-utils`)
  - Fedora: `sudo dnf install python3-gobject gtk3 pulseaudio-utils`
- An **OpenAI key** or an **OpenClicky account**, in `~/.openclicky/shell.json` — the same file the
  Mac app and the CLI read:

  ```json
  { "openaiApiKey": "sk-..." }
  ```

  or `"token"` (and `"backendUrl"` for your own backend). An own key goes straight to OpenAI and
  never to the backend. `"language": "hi-IN"` pins the language; `"linuxDictationKey": "Alt_R"`
  picks another key (any X keysym; a modifier key is best, since other keys auto-repeat).

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
| Tap twice, or esc | Cancel |
| Right ctrl + another key (a shortcut) | Not a take; nothing is typed |

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
they are skipped without it. They run the real app wiring end to end: XTEST presses the key, the
RECORD listener sees it, a stand-in microphone and engine answer, and the words land in a GTK text box.

## How it is put together

| File | Purpose |
|---|---|
| `controller.py` | One take at a time (idle → listening → finishing), the Mac's `DictationTakeController` in small. Reaches the desktop only through `DictationHost`. |
| `gestures.py` | Hold, tap, double tap, esc and "a shortcut, not a take" from raw key downs and ups, with the Mac's timings. |
| `x11.py` | The window in front (`_NET_ACTIVE_WINDOW`, `WM_CLASS`), the paste keystroke (XTEST), the listen-only key watcher (RECORD). |
| `desktop.py` | GTK 3: the clipboard paste and restore, the orb (a popup window that never takes the focus). |
| `recorder.py` | 16 kHz mono PCM from `parecord` or `arecord`, wrapped as WAV. |
| `transcriber.py` | Own OpenAI key → OpenAI; else account → `POST /agent/transcribe`; else a sentence naming what is missing. |
| `formatter.py` | The Mac's `TakeFormatter.formatLocally`, ported: shortcuts, fillers, dictionary, sentence case. |
| `config.py`, `space.py` | `~/.openclicky/shell.json` and the dictionary/shortcut files. |

Not yet: spoken numbers as digits, the model clean-up, history, the "is there a text box?" check
(AT-SPI), offline engines (Parakeet runs on Linux through sherpa-onnx), Wayland.
