"""Site assistant chat workflow: build a bounded prompt, call the LLM, check the answer.

Pure library code (ADR-003): the backend passes the provider, the curated page/site context and
the conversation; nothing here reads the database or user data.

Defences:
- The system prompt comes from the versioned prompt registry; user text is sanitised (control
  characters removed) and the conversation is trimmed to a fixed size before it is sent.
- Page context is a short server-curated description of the current page, never page contents.
- The only user detail ever included is a first name, when the caller chooses to pass it.
- A canary token in the system prompt detects prompt leakage; a leaking answer is replaced.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ielts_ai.prompts.registry import PromptRegistry
from ielts_ai.providers.base import LLMMessage, LLMProvider, LLMRequest

PROMPTS = PromptRegistry.from_directory(Path(__file__).resolve().parent.parent / "prompts")
PROMPT_KEY = "assistant.chat"
CANARY = "assistant-guide-7f3c"
FEATURE = "assistant.chat"

MAX_TURNS = 12  # most recent messages sent to the model (user + assistant)
MAX_MESSAGE_CHARS = 2000
MAX_CONTEXT_CHARS = 600

LEAK_REPLY = (
    "Sorry, I can't share details about how I work. I'm happy to help with IELTS questions or "
    "with using IELTS MASTER, though. What would you like to know?"
)


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AssistantContext:
    site_pages: str  # "- /path: description" lines, curated by the backend
    page: str | None = None  # curated description of the page the user is on
    first_name: str | None = None
    signed_in: bool = False


@dataclass(frozen=True)
class AssistantReply:
    text: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int


def clean(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = unicodedata.normalize("NFC", text)
    text = "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf"}
    )
    return text.strip()[:limit]


def build_messages(
    history: Sequence[ChatTurn], context: AssistantContext
) -> tuple[tuple[LLMMessage, ...], str]:
    template = PROMPTS.get(PROMPT_KEY)
    parts = [template.body.strip(), "Site pages:\n" + context.site_pages.strip()]
    situation = ["The learner is signed in." if context.signed_in else "The learner is a guest."]
    if context.first_name:
        situation.append(f"Their first name is {clean(context.first_name, 40)}.")
    if context.page:
        situation.append("They are currently on: " + clean(context.page, MAX_CONTEXT_CHARS))
    parts.append("Situation:\n" + " ".join(situation))
    messages = [LLMMessage(role="system", content="\n\n".join(parts))]
    turns = [t for t in history if clean(t.content)][-MAX_TURNS:]
    # The conversation must start with a user turn for most chat models.
    while turns and turns[0].role != "user":
        turns.pop(0)
    messages.extend(LLMMessage(role=t.role, content=clean(t.content)) for t in turns)
    return tuple(messages), template.version


async def reply(
    llm: LLMProvider,
    history: Sequence[ChatTurn],
    context: AssistantContext,
    *,
    correlation_id: str,
    max_output_tokens: int = 700,
) -> AssistantReply:
    messages, version = build_messages(history, context)
    if messages[-1].role != "user":
        raise ValueError("The conversation must end with a user message")
    response = await llm.generate(
        LLMRequest(
            feature=FEATURE,
            correlation_id=correlation_id,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=0.4,
        )
    )
    text = response.text.strip()
    if CANARY in text or "Honesty rules (most important)" in text:
        text = LEAK_REPLY
    return AssistantReply(
        text=text,
        model=response.model,
        prompt_version=version,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )
