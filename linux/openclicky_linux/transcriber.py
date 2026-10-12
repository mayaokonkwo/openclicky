"""Speech → text, routed the way the Mac app's `ProviderRouter` routes it: the person's own OpenAI
key straight to OpenAI (`/audio/transcriptions`, the model the backend uses), else the OpenClicky
backend on the account token (`POST /agent/transcribe`, base64 JSON), else a sentence naming what
is missing. Own keys never go to the backend.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from .config import LinuxSettings

TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
REQUEST_TIMEOUT_SECONDS = 30


class TranscriptionError(Exception):
    """Carries the sentence the orb shows."""


@dataclass(frozen=True)
class TranscriptionRoute:
    kind: str  # "openai" | "backend"
    request: urllib.request.Request


def multipart_form(fields: dict[str, str], file_field: str, file_name: str, file_bytes: bytes, file_mime: str) -> tuple[bytes, str]:
    boundary = f"openclicky-{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines += [f"--{boundary}".encode(), f'Content-Disposition: form-data; name="{name}"'.encode(), b"", value.encode()]
    lines += [
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"'.encode(),
        f"Content-Type: {file_mime}".encode(),
        b"",
        file_bytes,
        f"--{boundary}--".encode(),
        b"",
    ]
    return b"\r\n".join(lines), f"multipart/form-data; boundary={boundary}"


def route_for(wav_bytes: bytes, settings: LinuxSettings) -> TranscriptionRoute:
    if settings.openai_api_key:
        fields = {"model": TRANSCRIPTION_MODEL, "response_format": "json"}
        if settings.bare_language_code:
            fields["language"] = settings.bare_language_code
        body, content_type = multipart_form(fields, "file", "audio.wav", wav_bytes, "audio/wav")
        request = urllib.request.Request(OPENAI_TRANSCRIPTIONS_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": content_type})
        return TranscriptionRoute("openai", request)
    if settings.account_token:
        payload: dict[str, str] = {"audio": base64.b64encode(wav_bytes).decode("ascii"), "mime": "audio/wav"}
        if settings.bare_language_code:
            payload["language"] = settings.bare_language_code
        request = urllib.request.Request(f"{settings.backend_url}/agent/transcribe", data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {settings.account_token}", "Content-Type": "application/json"})
        return TranscriptionRoute("backend", request)
    raise TranscriptionError("dictation needs your openai key or an openclicky account: add openaiApiKey or token to ~/.openclicky/shell.json")


def transcribe(wav_bytes: bytes, settings: LinuxSettings) -> str:
    route = route_for(wav_bytes, settings)
    vendor = "openai" if route.kind == "openai" else "the openclicky backend"
    try:
        with urllib.request.urlopen(route.request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as refusal:
        if refusal.code == 401:
            raise TranscriptionError(f"{vendor} refused the key or token (401). check ~/.openclicky/shell.json") from refusal
        raise TranscriptionError(f"{vendor} could not transcribe ({refusal.code})") from refusal
    except (urllib.error.URLError, TimeoutError, OSError) as failure:
        raise TranscriptionError(f"couldn't reach {vendor}: {getattr(failure, 'reason', failure)}") from failure
    except ValueError as failure:
        raise TranscriptionError(f"{vendor} sent back something that isn't json") from failure
    text = answer.get("text") if isinstance(answer, dict) else None
    return text if isinstance(text, str) else ""
