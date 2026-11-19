"""Candidate input is data, never instructions (prompt-injection defence).

The response is wrapped in a delimiter the candidate cannot close: any occurrence of the
delimiter tag inside the text is neutralised before the prompt is built. The system prompt tells
the model to ignore instructions inside the delimited block, and the output is schema-validated
and cross-checked (excerpts must occur in the response) whatever the model says.
"""

import re
import unicodedata

TAG = "candidate_response"
_TAG_RE = re.compile(rf"</?\s*{TAG}\s*>", re.IGNORECASE)
_CONTROL = {"Cc", "Cf"}

# Words may contain an apostrophe (straight or typographic) or a hyphen: it's, isn't, well-known.
_WORD = re.compile("[A-Za-z0-9]+(?:['" + chr(0x2019) + "-][A-Za-z0-9]+)*")
MAX_RESPONSE_CHARS = 20_000
MIN_ASSESSABLE_WORDS = 20


class InputRejectedError(ValueError):
    """The response cannot be assessed (empty, too short, too long). Never scored."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def sanitize(text: str) -> str:
    """Normalise, drop control/format characters (keeping newlines/tabs), neutralise the tag."""
    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in _CONTROL)
    return _TAG_RE.sub("[tag removed]", text)


def check_response(text: str, *, min_words: int = MIN_ASSESSABLE_WORDS) -> str:
    if len(text) > MAX_RESPONSE_CHARS:
        raise InputRejectedError("too_long", "The response is too long to assess.")
    clean = sanitize(text).strip()
    if word_count(clean) < min_words:
        raise InputRejectedError(
            "too_short", f"At least {min_words} words are needed for an assessment."
        )
    return clean


def wrap(text: str) -> str:
    return f"<{TAG}>\n{text}\n</{TAG}>"
