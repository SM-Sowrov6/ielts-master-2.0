"""Answer normalisation, key notation and parsers (golden cases + property-based idempotence)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.content.question_types.normalize import (
    MAX_KEY_EXPANSIONS,
    KeyNotationError,
    ParsedDate,
    ParsedTime,
    TextRules,
    count_words,
    dates_equal,
    expand_key_notation,
    normalize_text,
    parse_date,
    parse_number,
    parse_time,
    times_equal,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  The   Library ", "the library"),
        ("library.", "library"),
        ("\u201cLibrary\u201d", "library"),  # typographic quotes
        ("well-known", "well known"),
        ("well \u2013 known", "well known"),  # en dash
        ("color", "colour"),
        ("Twenty-five", "25"),
        ("one hundred and five", "105"),
        ("1,250", "1250"),
        ("ﬁsh", "fish"),  # NFKC ligature
    ],
)
def test_normalize_text_golden(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_normalize_respects_strict_rules() -> None:
    strict = TextRules(
        case_sensitive=True, hyphen_policy="strict", british_american_equivalent=False
    )
    assert normalize_text("Well-Known", strict) == "Well-Known"
    assert normalize_text("color", strict) == "color"


@given(st.text(max_size=60))
def test_normalize_is_idempotent(value: str) -> None:
    once = normalize_text(value)
    assert normalize_text(once) == once


@pytest.mark.parametrize(
    ("notation", "expected"),
    [
        ("library", ["library"]),
        ("(the) library", ["the library", "library"]),
        ("colour/color", ["colour", "color"]),
        ("car park / parking lot", ["car park", "parking lot"]),
        (
            "(a) (short) break/rest",
            [
                "a short break",
                "a short rest",
                "a break",
                "a rest",
                "short break",
                "short rest",
                "break",
                "rest",
            ],
        ),
    ],
)
def test_key_notation_expansion(notation: str, expected: list[str]) -> None:
    assert expand_key_notation(notation) == expected


@pytest.mark.parametrize("bad", ["", "(the library", "the) x", "a//", "(a(b))"])
def test_key_notation_rejects_malformed(bad: str) -> None:
    with pytest.raises(KeyNotationError):
        expand_key_notation(bad)


def test_key_notation_caps_expansions() -> None:
    with pytest.raises(KeyNotationError, match=str(MAX_KEY_EXPANSIONS)):
        expand_key_notation(" ".join(f"({w})" for w in "abcdefg") + " x")  # 2**7 = 128 answers


@pytest.mark.parametrize(
    ("answer", "number_counts_as_word", "expected"),
    [
        ("library", False, 1),
        ("the library", False, 2),
        ("well-known", False, 1),
        ("25 cars", False, 1),
        ("25 cars", True, 2),
        ("25 30", False, 1),  # only one number is free
        ("twenty-five metres", False, 1),  # hyphenated number words are one number
    ],
)
def test_count_words(answer: str, number_counts_as_word: bool, expected: int) -> None:
    assert count_words(answer, number_counts_as_word=number_counts_as_word) == expected


def test_parse_number() -> None:
    assert parse_number("£1,250.50") == Decimal("1250.50")
    assert parse_number("twenty-five pounds") == Decimal("25")
    assert parse_number("none") is None


def test_parse_and_compare_times() -> None:
    assert parse_time("9.30") == ParsedTime(570, False)
    assert parse_time("9:30 pm") == ParsedTime(1290, True)
    assert parse_time("noon") == ParsedTime(720, True)
    assert parse_time("25:00") is None
    assert times_equal(ParsedTime(570, False), ParsedTime(570, True))
    assert times_equal(
        ParsedTime(570, False), ParsedTime(1290, True)
    )  # 9.30 vs 9.30pm (12h-modulo)
    assert not times_equal(ParsedTime(570, True), ParsedTime(1290, True))


def test_parse_and_compare_dates() -> None:
    assert parse_date("15th March") == ParsedDate(15, 3, None)
    assert parse_date("March 15, 2026") == ParsedDate(15, 3, 2026)
    assert parse_date("15/3/26") == ParsedDate(15, 3, 2026)
    assert parse_date("32 March") is None
    assert parse_date("next week") is None
    assert dates_equal(ParsedDate(15, 3, None), ParsedDate(15, 3, 2026))
    assert not dates_equal(ParsedDate(15, 3, 2026), ParsedDate(15, 3, None))
