"""Deterministic answer normalisation and parsing (docs/QUESTION_BANK_DESIGN.md §5).

Scoring never uses fuzzy matching: a response is correct only if its normalised form equals the
normalised form of an accepted answer. Key and response go through the same pipeline.
"""

import itertools
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

MAX_KEY_EXPANSIONS = 64

# Typographic quotes, dashes, minus sign and no-break space -> ASCII equivalents.
_TRANSLATE: dict[int, str] = {
    0x2018: "'",
    0x2019: "'",
    0x201C: '"',
    0x201D: '"',
    0x2013: "-",
    0x2014: "-",
    0x2212: "-",
    0x00A0: " ",
}
_EDGE_PUNCTUATION = ".,;:!?\"'()[]"
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")

# American -> British spelling equivalences applied to both sides (word level).
_SPELLING = {
    "color": "colour",
    "colors": "colours",
    "center": "centre",
    "centers": "centres",
    "meter": "metre",
    "meters": "metres",
    "liter": "litre",
    "liters": "litres",
    "theater": "theatre",
    "theaters": "theatres",
    "organize": "organise",
    "organized": "organised",
    "organization": "organisation",
    "organizations": "organisations",
    "analyze": "analyse",
    "analyzed": "analysed",
    "catalog": "catalogue",
    "traveling": "travelling",
    "traveled": "travelled",
    "traveler": "traveller",
    "favorite": "favourite",
    "neighbor": "neighbour",
    "neighbors": "neighbours",
    "behavior": "behaviour",
    "labor": "labour",
    "program": "programme",
    "programs": "programmes",
    "defense": "defence",
    "license": "licence",
    "jewelry": "jewellery",
    "gray": "grey",
    "aluminum": "aluminium",
}

_UNITS = {
    w: i
    for i, w in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
        ]
    )
}
_TENS = {
    w: (i + 2) * 10
    for i, w in enumerate(
        ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    )
}
_NUMBER_TOKEN = re.compile(r"^[£$€]?\d[\d.,:/]*(%|[a-z]{0,2})?$")

HyphenPolicy = Literal["equivalent", "strict"]


@dataclass(frozen=True, slots=True)
class TextRules:
    """Normalisation switches for text answers (from the question group's config)."""

    case_sensitive: bool = False
    hyphen_policy: HyphenPolicy = "equivalent"
    british_american_equivalent: bool = True
    numbers_as_digits_or_words: bool = True


def _basic(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).translate(_TRANSLATE)
    text = _THOUSANDS.sub("", text)
    return " ".join(text.split())


def _words_to_numbers(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] not in _UNITS and tokens[i] not in _TENS:
            out.append(tokens[i])
            i += 1
            continue
        total = current = 0
        j = i
        while j < len(tokens):
            word = tokens[j]
            if word in _UNITS:
                current += _UNITS[word]
            elif word in _TENS:
                current += _TENS[word]
            elif word == "hundred" and j > i:
                current *= 100
            elif word == "thousand" and j > i:
                total += current * 1000
                current = 0
            elif (
                word == "and"
                and j > i
                and j + 1 < len(tokens)
                and (tokens[j + 1] in _UNITS or tokens[j + 1] in _TENS)
            ):
                pass
            else:
                break
            j += 1
        out.append(str(total + current))
        i = j
    return out


def normalize_text(value: str, rules: TextRules = TextRules()) -> str:
    """Canonical comparison form of a free-text answer (idempotent)."""
    text = _basic(value)
    if not rules.case_sensitive:
        text = text.casefold()
    if rules.hyphen_policy == "equivalent":
        text = re.sub(r"\s*-\s*", " ", text)
    tokens = [token.strip(_EDGE_PUNCTUATION) for token in text.split()]
    tokens = [token for token in tokens if token]
    if rules.british_american_equivalent:
        tokens = [_SPELLING.get(token.casefold(), token) for token in tokens]
    if rules.numbers_as_digits_or_words:
        # Number words are matched in lower case; with case-sensitive rules only lower-case
        # number words convert, consistently for key and response.
        tokens = _words_to_numbers(tokens)
    return " ".join(tokens)


_SCALE_WORDS = {"hundred", "thousand", "and"}


def _is_number_token(token: str) -> bool:
    """'25', '£20', '9.30', 'twenty', 'twenty-five', 'one-hundred' count as numbers."""
    if _NUMBER_TOKEN.match(token):
        return True
    parts = token.split("-")
    return all(p in _UNITS or p in _TENS or p in _SCALE_WORDS for p in parts) and (
        parts[0] in _UNITS or parts[0] in _TENS
    )


def count_words(value: str, *, number_counts_as_word: bool) -> int:
    """IELTS word count: whitespace tokens, hyphenated compounds count once.

    With "AND/OR A NUMBER" instructions (`number_counts_as_word=False`) one numeric token is
    excluded from the count.
    """
    tokens = [t.strip(_EDGE_PUNCTUATION) for t in _basic(value).casefold().split()]
    tokens = [t for t in tokens if t]
    if number_counts_as_word:
        return len(tokens)
    numeric = [t for t in tokens if _is_number_token(t)]
    return len(tokens) - min(1, len(numeric))


def parse_number(value: str) -> Decimal | None:
    text = _basic(value).casefold().replace("£", "").replace("$", "").replace("€", "")
    text = " ".join(_words_to_numbers(re.sub(r"\s*-\s*", " ", text).split()))
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match is None:
        return None
    try:
        return Decimal(match.group())
    except InvalidOperation:  # pragma: no cover - regex guarantees a valid literal
        return None


_TIME = re.compile(r"^(\d{1,2})(?:[.:](\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?$")


@dataclass(frozen=True, slots=True)
class ParsedTime:
    minutes: int
    has_meridiem: bool


def parse_time(value: str) -> ParsedTime | None:
    """Accepts 9.30, 9:30, 9.30am, 9 pm, noon/midday, midnight. Spoken forms need key variants."""
    text = _basic(value).casefold().strip(" .")
    if text in ("noon", "midday", "12 noon"):
        return ParsedTime(12 * 60, True)
    if text == "midnight":
        return ParsedTime(0, True)
    match = _TIME.match(text)
    if match is None:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2) or 0)
    meridiem = match.group(3)
    if minutes > 59 or hours > 23 or (meridiem and not 1 <= hours <= 12):
        return None
    if meridiem:
        is_pm = meridiem.startswith("p")
        hours = (hours % 12) + (12 if is_pm else 0)
    return ParsedTime(hours * 60 + minutes, meridiem is not None)


def times_equal(key: ParsedTime, response: ParsedTime) -> bool:
    if key.has_meridiem == response.has_meridiem:
        return key.minutes == response.minutes
    return key.minutes % 720 == response.minutes % 720


_MONTHS = {
    name: index
    for index, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}


@dataclass(frozen=True, slots=True)
class ParsedDate:
    day: int
    month: int
    year: int | None


def parse_date(value: str) -> ParsedDate | None:
    """Accepts '15 March', '15th March 2025', 'March 15', '15/3', '15/03/2025' (day first)."""
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", _basic(value).casefold()).replace(",", " ")
    tokens = text.split()
    numeric = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?", text.strip())
    day: int | None = None
    month: int | None = None
    year: int | None = None
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        year = int(numeric.group(3)) if numeric.group(3) else None
    elif 2 <= len(tokens) <= 3:
        if tokens[0].isdigit() and tokens[1] in _MONTHS:
            day, month = int(tokens[0]), _MONTHS[tokens[1]]
        elif tokens[0] in _MONTHS and tokens[1].isdigit():
            day, month = int(tokens[1]), _MONTHS[tokens[0]]
        if len(tokens) == 3:
            year = int(tokens[2]) if tokens[2].isdigit() else -1
    if day is None or month is None or year == -1:
        return None
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    if year is not None and year < 100:
        year += 2000
    return ParsedDate(day, month, year)


def dates_equal(key: ParsedDate, response: ParsedDate) -> bool:
    if (key.day, key.month) != (response.day, response.month):
        return False
    return key.year is None or key.year == response.year


class KeyNotationError(ValueError):
    pass


def expand_key_notation(notation: str) -> list[str]:
    """Expand answer-key notation into concrete accepted answers (QUESTION_BANK_DESIGN.md §5.2).

    - `(the) library`      -> optional word: "the library", "library"
    - `colour/color`       -> word-level alternatives (slash without spaces)
    - `car park / parking lot` -> phrase-level alternatives (slash with spaces)
    The first result (all optional words included, first alternatives) is the canonical answer.
    """
    text = " ".join(notation.split())
    if not text:
        raise KeyNotationError("empty answer")
    if text.count("(") != text.count(")"):
        raise KeyNotationError(f"unbalanced parentheses in {notation!r}")
    results: list[str] = []
    for phrase in (p.strip() for p in re.split(r"\s+/\s+", text)):
        choices: list[list[str]] = []
        for token in phrase.split():
            optional = token.startswith("(") and token.endswith(")")
            core = token[1:-1] if optional else token
            if "(" in core or ")" in core:
                raise KeyNotationError(f"nested or partial parentheses in {notation!r}")
            alternatives = core.split("/")
            if not all(alternatives):
                raise KeyNotationError(f"empty alternative in {notation!r}")
            choices.append(alternatives + ([""] if optional else []))
        for combination in itertools.product(*choices):
            answer = " ".join(part for part in combination if part)
            if answer and answer not in results:
                results.append(answer)
                if len(results) > MAX_KEY_EXPANSIONS:
                    raise KeyNotationError(
                        f"{notation!r} expands to more than {MAX_KEY_EXPANSIONS} answers"
                    )
    return results
