"""Truth tables for all 18 question-type handlers (docs/QUESTION_BANK_DESIGN.md §10)."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from app.modules.content.question_types import REGISTRY, get_handler
from app.modules.content.question_types.base import (
    GroupDTO,
    KeyDTO,
    OptionDTO,
    QuestionDTO,
    ResponseError,
    ValidationIssue,
)
from app.modules.content.question_types.catalog import TYPE_MODULES

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
FORBIDDEN_VIEW_KEYS = {
    "keys",
    "canonical_value",
    "variants",
    "explanation",
    "accepted",
    "notation",
    "answer_keys",
}

ABC = tuple(OptionDTO(letter, f"Synthetic option {letter}") for letter in "ABC")
ABCDE = tuple(OptionDTO(letter, f"Synthetic option {letter}") for letter in "ABCDE")


def _q(
    keys: tuple[KeyDTO, ...], *, number: int = 1, options: tuple[OptionDTO, ...] = ()
) -> QuestionDTO:
    return QuestionDTO(number_from=number, number_to=number, marks=1, keys=keys, options=options)


def _option_key(value: str) -> tuple[KeyDTO, ...]:
    return (KeyDTO(1, value, "option"),)


def sample(code: str) -> tuple[GroupDTO, QuestionDTO, Any, Any]:
    """(group, question, correct response, wrong response) for each type."""
    handler = REGISTRY[code]
    if code == "mcq_multi":
        question = QuestionDTO(
            number_from=21,
            number_to=22,
            marks=2,
            keys=(KeyDTO(1, "A", "set_member"), KeyDTO(2, "D", "set_member")),
        )
        group = GroupDTO(code, options=ABCDE, questions=(question,))
        return group, question, {"choices": ["D", "A"]}, {"choices": ["B", "C"]}
    if code in ("tfng", "ynng"):
        answer = "TRUE" if code == "tfng" else "YES"
        question = _q(_option_key(answer))
        return (
            GroupDTO(code, questions=(question,)),
            question,
            {"choice": answer.lower()},
            {"choice": "NOT GIVEN"},
        )
    if handler.family == "option":
        if code == "mcq_single":
            question = _q(_option_key("B"), options=ABC)
            return GroupDTO(code, questions=(question,)), question, {"choice": "b"}, {"choice": "C"}
        question = _q(_option_key("B"))
        return (
            GroupDTO(code, options=ABC, questions=(question,)),
            question,
            {"choice": "B"},
            {"choice": "A"},
        )
    # text family (and text_or_option types in their default text format)
    question = _q((KeyDTO(1, "the library", "text", ("library",)),))
    group = GroupDTO(code, config={"word_limit": 2}, questions=(question,))
    return group, question, {"text": "  Library. "}, {"text": "museum"}


def _errors(issues: list[ValidationIssue]) -> list[str]:
    return [f"{i.code}@{i.location}" for i in issues if i.is_error]


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _walk_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _walk_keys(v)}
    return set()


def test_registry_catalog_and_migration_seed_agree() -> None:
    path = next(MIGRATIONS.glob("*_0004_seed_question_types.py"))
    spec = importlib.util.spec_from_file_location("seed_0004", path)
    assert spec is not None
    assert spec.loader is not None
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    seeded = {code: (family, frozenset(modules)) for code, family, modules in seed.QUESTION_TYPES}
    assert len(REGISTRY) == 18
    assert set(seeded) == set(REGISTRY) == set(TYPE_MODULES)
    for code, (family, modules) in seeded.items():
        handler_family = REGISTRY[code].family
        expected = (
            "text_or_option" if getattr(REGISTRY[code], "allow_option", False) else handler_family
        )
        assert family == expected, code
        assert modules == TYPE_MODULES[code], code


@pytest.mark.parametrize("code", sorted(REGISTRY))
def test_truth_table(code: str) -> None:
    handler = get_handler(code)
    group, question, correct, wrong = sample(code)
    assert _errors(handler.validate_authoring(group, "g")) == []

    right = handler.score(group, question, correct)
    assert (right.marks_awarded, right.is_correct, right.reason) == (
        question.marks,
        True,
        "correct",
    )
    miss = handler.score(group, question, wrong)
    assert (miss.marks_awarded, miss.is_correct, miss.reason) == (0, False, "incorrect")
    empty = handler.score(group, question, None)
    assert (empty.marks_awarded, empty.reason) == (0, "no_response")


@pytest.mark.parametrize("code", sorted(REGISTRY))
def test_student_view_never_leaks_answers(code: str) -> None:
    group, question, _, _ = sample(code)
    view = get_handler(code).student_view(group)
    assert not (_walk_keys(view) & FORBIDDEN_VIEW_KEYS)
    if REGISTRY[code].family == "text":
        serialized = json.dumps(view)
        assert all(answer not in serialized for answer in question.keys[0].accepted)


def test_multi_option_partial_credit_and_response_rules() -> None:
    handler = get_handler("mcq_multi")
    group, question, _, _ = sample("mcq_multi")
    partial = handler.score(group, question, {"choices": ["A", "B"]})
    assert (partial.marks_awarded, partial.is_correct, partial.reason) == (1, False, "partial")
    for bad, code in [
        ({"choices": ["A", "B", "D"]}, "too_many_choices"),
        ({"choices": ["A", "a"]}, "duplicate_choice"),
        ({"choices": ["Z"]}, "unknown_option"),
        ({"choice": "A"}, "response_invalid"),
    ]:
        with pytest.raises(ResponseError) as excinfo:
            handler.score(group, question, bad)
        assert excinfo.value.code == code


def test_multi_option_authoring_rules() -> None:
    handler = get_handler("mcq_multi")
    question = QuestionDTO(
        number_from=1, number_to=2, marks=2, keys=(KeyDTO(1, "A", "set_member"),)
    )
    errors = _errors(
        handler.validate_authoring(GroupDTO("mcq_multi", options=ABC, questions=(question,)), "g")
    )
    assert any(e.startswith("key_count") for e in errors)


def test_option_rules() -> None:
    handler = get_handler("matching_headings")
    q1, q2 = _q(_option_key("B"), number=1), _q(_option_key("B"), number=2)
    group = GroupDTO(
        "matching_headings", config={"options_reusable": False}, options=ABC, questions=(q1, q2)
    )
    assert any(
        e.startswith("option_reused") for e in _errors(handler.validate_authoring(group, "g"))
    )
    bad_key = GroupDTO("matching_headings", options=ABC, questions=(_q(_option_key("Z")),))
    assert any(
        e.startswith("key_not_an_option") for e in _errors(handler.validate_authoring(bad_key, "g"))
    )
    with pytest.raises(ResponseError, match="not an option"):
        handler.score(bad_key, bad_key.questions[0], {"choice": "Q"})


def test_fixed_choice_types_reject_authored_options() -> None:
    handler = get_handler("tfng")
    group = GroupDTO("tfng", options=ABC, questions=(_q(_option_key("TRUE")),))
    assert any(
        e.startswith("options_not_allowed") for e in _errors(handler.validate_authoring(group, "g"))
    )
    wrong_key = GroupDTO("tfng", questions=(_q(_option_key("YES")),))
    assert any(
        e.startswith("key_not_an_option")
        for e in _errors(handler.validate_authoring(wrong_key, "g"))
    )


def test_text_word_limit_applies_to_responses_and_keys() -> None:
    handler = get_handler("sentence_completion")
    group, question, _, _ = sample("sentence_completion")
    over = handler.score(group, question, {"text": "the big library"})
    assert (over.marks_awarded, over.reason) == (0, "over_word_limit")
    long_key = _q((KeyDTO(1, "the central city library", "text"),))
    issues = handler.validate_authoring(
        GroupDTO("sentence_completion", config={"word_limit": 2}, questions=(long_key,)), "g"
    )
    assert any(e.startswith("key_exceeds_word_limit") for e in _errors(issues))


def test_text_number_rule_and_alternative_spellings() -> None:
    handler = get_handler("note_completion")
    question = _q((KeyDTO(1, "25 metres", "text"),))
    group = GroupDTO(
        "note_completion", config={"word_limit": 1, "allow_number": True}, questions=(question,)
    )
    assert _errors(handler.validate_authoring(group, "g")) == []
    assert handler.score(group, question, {"text": "twenty-five meters"}).is_correct


@pytest.mark.parametrize(
    ("mode", "key", "right", "wrong"),
    [
        ("numeric", "1250", "£1,250", "1205"),
        ("time", "9.30", "9:30 am", "10.30"),
        ("date", "15 March", "March 15th", "16 March"),
    ],
)
def test_structured_match_modes(mode: str, key: str, right: str, wrong: str) -> None:
    handler = get_handler("form_completion")
    question = _q((KeyDTO(1, key, mode),))
    group = GroupDTO("form_completion", questions=(question,))
    assert _errors(handler.validate_authoring(group, "g")) == []
    assert handler.score(group, question, {"text": right}).is_correct
    assert not handler.score(group, question, {"text": wrong}).is_correct


def test_unparseable_structured_key_is_an_authoring_error() -> None:
    handler = get_handler("form_completion")
    group = GroupDTO("form_completion", questions=(_q((KeyDTO(1, "soon", "time"),)),))
    assert any(
        e.startswith("key_unparseable") for e in _errors(handler.validate_authoring(group, "g"))
    )


def test_word_bank_format_only_for_types_that_allow_it() -> None:
    bank = GroupDTO(
        "summary_completion",
        config={"answer_format": "option"},
        options=ABC,
        questions=(_q(_option_key("A")),),
    )
    assert _errors(get_handler("summary_completion").validate_authoring(bank, "g")) == []
    assert (
        get_handler("summary_completion").score(bank, bank.questions[0], {"choice": "A"}).is_correct
    )
    not_allowed = GroupDTO(
        "note_completion",
        config={"answer_format": "option"},
        options=ABC,
        questions=(_q(_option_key("A")),),
    )
    assert any(
        e.startswith("answer_format_invalid")
        for e in _errors(get_handler("note_completion").validate_authoring(not_allowed, "g"))
    )


def test_template_blanks_must_match_question_numbers() -> None:
    template = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Rent: "},
                    {"type": "blank", "attrs": {"number": 7}},
                ],
            }
        ],
    }
    handler = get_handler("note_completion")
    questions = (_q((KeyDTO(1, "x", "text"),), number=7), _q((KeyDTO(1, "y", "text"),), number=8))
    group = GroupDTO("note_completion", config={"template": template}, questions=questions)
    assert any(
        e.startswith("template_blanks_mismatch")
        for e in _errors(handler.validate_authoring(group, "g"))
    )


def test_unknown_config_keys_are_rejected() -> None:
    group, _, _, _ = sample("short_answer")
    bad = GroupDTO(
        "short_answer", config={"word_limit": 2, "surprise": True}, questions=group.questions
    )
    assert any(
        e.startswith("group_config_invalid")
        for e in _errors(get_handler("short_answer").validate_authoring(bad, "g"))
    )
