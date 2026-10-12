"""Asking about the screen by text: the question and a screenshot go to a model, which answers in a
sentence or two and may start with a `[POINT:…]` tag the pointer flies to.

Routed like the Mac app's ask lane: the person's own Anthropic key straight to Anthropic (Messages,
the Mac's default model), else an own OpenAI key to OpenAI chat completions, else the OpenClicky
account through the backend's `POST /chat` (the same Messages body the Mac relays), else a sentence
naming what is missing. Own keys never go to the backend. Answers are not streamed: they are short,
and the caption shows them whole.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .config import LinuxSettings

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4.1"
MAX_ANSWER_TOKENS = 400
REQUEST_TIMEOUT_SECONDS = 60
# Exchanges kept for follow-ups ("and where is that?"), as on the Mac.
HISTORY_EXCHANGES = 10

# The Mac app's ask prompt, for a typed question and an answer that is read, not heard.
SYSTEM_PROMPT = """you're openclicky, a friendly companion living on the user's linux desktop. the user just typed a question to you and you can see their screen. your answer is shown in a small caption next to your pointer, so keep it short. this is an ongoing conversation, you remember everything they've said before.

rules:
- keep it short: one or two short sentences, about thirty words at most.
- if they ask you to explain more or go deeper, say more, but still keep it under about eighty words.
- all lowercase, casual, warm. no emojis.
- no lists, bullet points, markdown or em dashes. plain sentences.
- if the user's question relates to what's on their screen, reference specific things you see.
- if the screenshot doesn't seem relevant to their question, just answer the question directly.
- you can help with anything: coding, writing, general knowledge, brainstorming.
- never say "simply" or "just".
- don't end with questions like "want me to explain more?", and don't add extra tips they didn't ask for.

element pointing:
you have a small orange triangle pointer that can fly to and point at things on screen. use it whenever pointing would genuinely help: if they're asking how to do something, looking for a menu, trying to find a button, or need help navigating an app, point at the relevant element. err on the side of pointing. don't point for general knowledge questions or at something obvious they're already looking at.

when you point, START your response with a coordinate tag. the screenshot is labeled with its pixel size; use it as the coordinate space, origin (0,0) at the top-left, x rightward, y downward.

format: [POINT:x,y:label] where x,y are integer pixel coordinates in the screenshot and label is a short 1-3 word description of the element (like "search bar" or "save button").

if pointing wouldn't help, start with [POINT:none].

examples:
- user asks how to open a new tab in firefox: "[POINT:1180,40:new tab] that plus sign at the end of your tabs opens a new one."
- user asks what html is: "[POINT:none] html stands for hypertext markup language, it's basically the skeleton of every web page."
"""


class AskError(Exception):
    """Carries the sentence the caption shows."""


@dataclass(frozen=True)
class Screenshot:
    png_bytes: bytes
    width: int
    height: int
    # Screenshot pixels per screen pixel (below 1 when the capture was downscaled).
    scale: float


@dataclass(frozen=True)
class AskRequest:
    kind: str  # "anthropic" | "openai" | "backend"
    request: urllib.request.Request


@dataclass
class Conversation:
    exchanges: list[tuple[str, str]] = field(default_factory=list)

    def remember(self, question: str, answer: str) -> None:
        self.exchanges.append((question, answer))
        del self.exchanges[:-HISTORY_EXCHANGES]


def _with_language(settings: LinuxSettings) -> str:
    if settings.language_code and settings.bare_language_code != "en":
        return SYSTEM_PROMPT + f"\nalways answer in the language with code {settings.language_code}, whatever language the question is in."
    return SYSTEM_PROMPT


def _anthropic_body(question: str, screenshot: Screenshot, conversation: Conversation, settings: LinuxSettings) -> dict:
    messages = []
    for earlier_question, earlier_answer in conversation.exchanges:
        messages += [{"role": "user", "content": earlier_question}, {"role": "assistant", "content": earlier_answer}]
    messages.append({"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(screenshot.png_bytes).decode("ascii")}},
        {"type": "text", "text": f"screen 1 (primary focus, {screenshot.width}x{screenshot.height} pixels)\n\n{question}"},
    ]})
    return {"model": ANTHROPIC_MODEL, "max_tokens": MAX_ANSWER_TOKENS, "system": _with_language(settings), "messages": messages}


def _openai_body(question: str, screenshot: Screenshot, conversation: Conversation, settings: LinuxSettings) -> dict:
    messages: list[dict] = [{"role": "system", "content": _with_language(settings)}]
    for earlier_question, earlier_answer in conversation.exchanges:
        messages += [{"role": "user", "content": earlier_question}, {"role": "assistant", "content": earlier_answer}]
    image_url = "data:image/png;base64," + base64.b64encode(screenshot.png_bytes).decode("ascii")
    messages.append({"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_url}},
        {"type": "text", "text": f"screen 1 (primary focus, {screenshot.width}x{screenshot.height} pixels)\n\n{question}"},
    ]})
    return {"model": OPENAI_MODEL, "max_tokens": MAX_ANSWER_TOKENS, "messages": messages}


def request_for(question: str, screenshot: Screenshot, conversation: Conversation, settings: LinuxSettings) -> AskRequest:
    if settings.anthropic_api_key:
        body = json.dumps(_anthropic_body(question, screenshot, conversation, settings)).encode()
        return AskRequest("anthropic", urllib.request.Request(ANTHROPIC_MESSAGES_URL, data=body, method="POST", headers={
            "x-api-key": settings.anthropic_api_key, "anthropic-version": ANTHROPIC_VERSION, "Content-Type": "application/json"}))
    if settings.openai_api_key:
        body = json.dumps(_openai_body(question, screenshot, conversation, settings)).encode()
        return AskRequest("openai", urllib.request.Request(OPENAI_CHAT_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}))
    if settings.account_token:
        body = json.dumps(_anthropic_body(question, screenshot, conversation, settings)).encode()
        return AskRequest("backend", urllib.request.Request(f"{settings.backend_url}/chat", data=body, method="POST", headers={
            "Authorization": f"Bearer {settings.account_token}", "anthropic-version": ANTHROPIC_VERSION, "Content-Type": "application/json"}))
    raise AskError("asking needs an anthropic or openai key, or an openclicky account. add one in settings.")


def answer_text(kind: str, response: dict) -> str:
    if kind == "openai":
        choices = response.get("choices") or []
        content = choices[0].get("message", {}).get("content") if choices else None
        return content.strip() if isinstance(content, str) else ""
    blocks = response.get("content") or []
    return "".join(block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text").strip()


def ask(question: str, screenshot: Screenshot, conversation: Conversation, settings: LinuxSettings) -> str:
    routed = request_for(question, screenshot, conversation, settings)
    vendor = {"anthropic": "anthropic", "openai": "openai", "backend": "the openclicky backend"}[routed.kind]
    try:
        with urllib.request.urlopen(routed.request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as refusal:
        if refusal.code == 401:
            raise AskError(f"{vendor} refused the key or token. check it in settings.") from refusal
        if refusal.code == 402 and routed.kind == "backend":
            raise AskError("your openclicky allowance is used up for now.") from refusal
        raise AskError(f"{vendor} couldn't answer ({refusal.code}).") from refusal
    except (urllib.error.URLError, TimeoutError, OSError) as failure:
        raise AskError(f"couldn't reach {vendor}.") from failure
    except ValueError as failure:
        raise AskError(f"{vendor} sent back something that isn't json.") from failure
    text = answer_text(routed.kind, answer if isinstance(answer, dict) else {})
    if not text:
        raise AskError(f"{vendor} answered with no text.")
    return text
