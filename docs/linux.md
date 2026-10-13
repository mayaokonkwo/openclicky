# OpenClicky on Linux

An early Linux client for OpenClicky. It runs against the same backend contract and reads the same
`~/.openclicky` files as the Mac app, but is its own small program: Python and GTK 3 on X11, under
[`linux/`](../linux). Everything in the main README is about the Mac app; this page is the Linux one.

What it does today: **ask about your screen by text** (the pointer answers and points), **step by
step guidance**, **the pointer** itself (including shake to appear), **dictation** (untested with a
real microphone so far), **Settings** and a **tray icon**. Not yet: spoken answers, asking by voice,
Wayland.

## Ask about your screen

Tap **left ctrl twice**. A one-line box opens at the top of the screen:

![The ask box over a notes app, with "where do i save this?" typed in](media/linux/ask-box.png)

Press **Enter**. The box closes, a screenshot of your screen goes with the question, and the orange
pointer beside your mouse says "thinking…". With more than one monitor, each one goes as its own
picture, the one with your mouse first, and the pointer can fly to another monitor when that is
where the answer is. When the answer is about something on screen, the
pointer flies to it and types the answer beside itself:

![The pointer on the notes app's Save button, with a caption saying the save button will do it](media/linux/ask-answer.png)

*A real answer (Claude Sonnet 4.6 through OpenRouter) about the window on screen; the pointer's tip
is on the Save button the answer names.* A question that is not about the screen ("what is the
capital of france?") is answered by the mouse without pointing. **Esc** dismisses an answer and the
pointer comes back to the mouse. Follow-ups remember the last ten exchanges.

## Step by step

Ask how to do something that takes several steps ("how do i turn on dark mode?") and you get one
step at a time: the pointer shows the first one and waits. Do it — a click, or Return or Tab after
typing — and a moment later, once the menu or dialog has opened, OpenClicky looks at your screen
again and shows the next step, until the last one:

![A Photos settings dialog opened by the first step, with the pointer on its Dark mode checkbox and the caption "check that dark mode checkbox."](media/linux/guided-step.png)

*The second step of a real guide: the first ("open settings first.") pointed at the Settings button,
whose click opened this dialog.* If you click something else, the next step helps you back. **Esc**,
a new question, two minutes without a click, or fifteen steps end the guide. Steps work the way they
do in the Mac app.

## The pointer

A small orange triangle that follows the mouse, a little below and to the right of it. Clicks go
straight through it, and it never takes the keyboard. **Settings → Show the pointer** decides when it
shows while it is following you; while it is answering or pointing it always shows.

| Show the pointer | What it does |
|---|---|
| always, beside the mouse | The default. |
| while the mouse moves | Fades away once the mouse has rested for 3 seconds; any movement brings it back. |
| after a shake | Out of sight until you **shake the mouse** quickly side to side, then it follows until the mouse rests. An ordinary back-and-forth never counts (four quick turns of at least 60 px are needed, as on the Mac). |
| only while answering | Out of sight until an answer shows. |

## Dictate

Hold **right ctrl**, speak, let go. The orb at the bottom of the screen shows what is happening:

![A notes app with the orb at the bottom saying "listening · release to transcribe"](media/linux/dictation-listening.png)

Your words are cleaned up the way the Mac app cleans them (fillers such as "um" removed, your
dictionary and spoken shortcuts from `~/.openclicky/dictation/`, a capital at the start of each
sentence) and typed where your cursor is:

![The same app with "And two lemons" typed on a new line and the orb saying "moved to text box"](media/linux/dictation-done.png)

*Taken with a stand-in microphone that "heard" "um, and two lemons": dictation has not yet been
tried with a real microphone.*

| Do | Get |
|---|---|
| Hold right ctrl, speak, let go | The words are typed into the window in front |
| Tap right ctrl, speak, tap again | The same, without holding the key |
| Tap right ctrl twice, or press esc | Cancel |
| Right ctrl + another key | A shortcut, not dictation: nothing is typed |

The words go only into the window that was in front when you pressed the key. If another window is
in front by the time they are ready, they are put on the clipboard instead ("copied, press ctrl+v").
Terminals get ctrl+shift+v. Your own clipboard text is put back afterwards.

## Settings

From the tray icon (**Settings…**), or `openclicky-linux settings`:

![The Settings window: dictation key, language, show the pointer, and the keys](media/linux/settings.png)

*Shown with an example key, not a real one.* Below the fields it says where dictation and answers
will go, as you type. **Save** writes into `~/.openclicky/shell.json`, the file the Mac app and the
CLI read, and leaves everything else in it alone; the file stays readable by you only.

| You add | Answers come from | Dictation goes to |
|---|---|---|
| an Anthropic key | Anthropic (Claude Sonnet 4.6) | — |
| an OpenRouter key | OpenRouter (Claude Sonnet 4.6, or `answerModels.openrouter`) | — |
| an OpenAI key | OpenAI (GPT-4.1) | OpenAI (`gpt-4o-mini-transcribe`) |
| an OpenClicky account token | the OpenClicky backend (`/chat`) | the OpenClicky backend (`/agent/transcribe`) |

With several, answers use the first in that order, as the Mac app does. Your own keys go straight
to their company and never to the OpenClicky backend.

## Install

You need an **X11 session** (at the login screen, pick the session called "Xorg" or "X11" rather
than "Wayland"). Wayland does not let an app watch a key, type into another app or float a window
over it; on Wayland OpenClicky says so and stops.

1. From your distribution: Python 3.10+, GTK 3 bindings and a recorder.
   - Debian, Ubuntu: `sudo apt install python3-venv python3-gi gir1.2-gtk-3.0 pulseaudio-utils`
   - Fedora: `sudo dnf install python3-gobject gtk3 pulseaudio-utils`
2. Download `openclicky_linux-0.1.0-py3-none-any.whl` from the release, then:

   ```bash
   python3 -m venv --system-site-packages ~/.local/openclicky
   ~/.local/openclicky/bin/pip install openclicky_linux-0.1.0-py3-none-any.whl
   ~/.local/openclicky/bin/openclicky-linux settings   # add a key, then Save
   ~/.local/openclicky/bin/openclicky-linux --check    # what it found
   ~/.local/openclicky/bin/openclicky-linux
   ```

   From a clone instead: `cd linux && python3 -m venv --system-site-packages .venv && .venv/bin/pip install -e .`

`--system-site-packages` lets the program use your distribution's GTK. Ctrl+C in the terminal, or
**Quit** in the tray menu, stops it. The tray icon needs a system tray (Xfce, KDE, MATE and Cinnamon
have one; GNOME needs an extension); without one, the shortcuts still work and Settings opens with
`openclicky-linux settings`.

## Privacy

- A question sends a screenshot of **every monitor** to whoever answers it (on an OpenClicky
  account, the two nearest your mouse): keep anything private out of sight before you ask.
- Dictation sends only the audio recorded while you hold the key.
- Nothing is recorded or sent otherwise: the watcher only notices key presses and clicks (it acts on
  clicks only while a guide waits for a step), and the pointer only reads where your mouse is.
- A guide sends a fresh screenshot after each step you do, until it ends.
- Keys live in `~/.openclicky/shell.json`, readable by your user only.

## When something does not work

| You see | Try |
|---|---|
| "needs an X11 session" | Log out and pick the Xorg / X11 session. |
| "asking needs an anthropic, openrouter or openai key…" | Add a key in Settings. |
| "no microphone recorder found" | Install `pulseaudio-utils` (or `alsa-utils`). |
| "didn't catch that" every time | Check the microphone in your sound settings. In a virtual machine, the host must pass the microphone through. |
| The pointer never shows | Settings → Show the pointer: "after a shake" and "only while answering" keep it hidden on purpose. |
| Left ctrl twice does nothing | Tap, don't hold, and press nothing in between: ctrl+C never counts. |

`openclicky-linux --check` prints what it found: the key, the recorder, where dictation and answers
go, the language and the pointer setting.

## For developers

How it is built, which Mac file each part follows, and how to run the tests (they start their own
private X display, so they never touch yours): [`linux/README.md`](../linux/README.md). The pictures
on this page are made by `linux/scripts/make-doc-screenshots.sh`.
