"""Settings, read from the same `~/.openclicky/shell.json` the Mac app and the CLI use.

Keys read here: `openaiApiKey` (own key, sent straight to OpenAI), `token` and `backendUrl` (an
OpenClicky account, the fallback), `language` (the dictation language; English when unset), and the
Linux-only `linuxDictationKey` (an X keysym name, `Control_R` by default: Linux never sees fn).
`BACKEND_URL` and `OPENCLICKY_OPENAI_KEY` in the environment win over the file, as on the Mac.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

HOSTED_BACKEND_URL = "https://api.openclicky.flowsxr.com"
DEFAULT_DICTATION_KEY = "Control_R"


def openclicky_directory() -> Path:
    return Path(os.environ.get("OPENCLICKY_HOME", Path.home() / ".openclicky"))


@dataclass(frozen=True)
class LinuxSettings:
    openai_api_key: str | None = None
    account_token: str | None = None
    backend_url: str = HOSTED_BACKEND_URL
    language_code: str | None = None
    dictation_key: str = DEFAULT_DICTATION_KEY

    @property
    def bare_language_code(self) -> str | None:
        """"en-IN" → "en": the transcription APIs take the language alone."""
        if not self.language_code:
            return None
        return self.language_code.split("-")[0].split("_")[0].lower() or None


def _cleaned(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def load_settings(shell_json_path: Path | None = None, environment: dict[str, str] | None = None) -> LinuxSettings:
    path = shell_json_path or openclicky_directory() / "shell.json"
    environment = os.environ if environment is None else environment
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, ValueError):
        raw = {}
    backend_url = _cleaned(environment.get("BACKEND_URL")) or _cleaned(raw.get("backendUrl")) or HOSTED_BACKEND_URL
    return LinuxSettings(
        openai_api_key=_cleaned(environment.get("OPENCLICKY_OPENAI_KEY")) or _cleaned(raw.get("openaiApiKey")),
        account_token=_cleaned(raw.get("token")),
        backend_url=backend_url.rstrip("/"),
        language_code=_cleaned(raw.get("language")),
        dictation_key=_cleaned(raw.get("linuxDictationKey")) or DEFAULT_DICTATION_KEY,
    )
