"""Synthetic Reading content for tests ONLY (invented text, D-04): 3 passages, 40 questions,
every Reading-capable registry type, plus the correct candidate responses."""

import copy
from typing import Any

from content_fixtures import doc

READING_TYPES = {
    "tfng", "ynng", "matching_headings", "matching_information", "matching_features",
    "matching_sentence_endings", "sentence_completion", "summary_completion", "note_completion",
    "table_completion", "flowchart_completion", "diagram_labelling", "short_answer",
    "mcq_single", "mcq_multi",
}  # fmt: skip


def _passage(n: int) -> dict[str, Any]:
    paragraphs = [
        {"label": label, "text": f"Synthetic paragraph {label} of passage {n}. " * 6}
        for label in "ABCDEF"
    ]
    return {
        "title": f"Synthetic passage {n}",
        "body": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": p["text"]}]}
                for p in paragraphs
            ],
        },
        "paragraphs": paragraphs,
    }


def _q(n: int, answer: str, **extra: Any) -> dict[str, Any]:
    return {
        "number_from": n,
        "stem": doc(f"Synthetic statement {n}."),
        "answers": [{"value": answer}],
        "explanation": {
            "body": doc(f"Synthetic explanation {n}."),
            "evidence_paragraph_label": "A",
        },
        **extra,
    }


def _opts(labels: str | list[str]) -> list[dict[str, str]]:
    return [{"label": label, "text": f"Synthetic option {label}"} for label in labels]


ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii"]

# number -> correct candidate response
ANSWERS: dict[int, dict[str, Any]] = {}


def _group(qtype: str, numbers: list[int], answers: list[str], **group: Any) -> dict[str, Any]:
    text = qtype.endswith("_completion") or qtype in ("short_answer", "diagram_labelling")
    for n, a in zip(numbers, answers, strict=True):
        ANSWERS[n] = {"text": a} if text else {"choice": a}
    return {
        "question_type": qtype,
        "instructions": f"Synthetic instructions for {qtype}.",
        **group,
        "questions": [_q(n, a) for n, a in zip(numbers, answers, strict=True)],
    }


def reading_sections() -> list[dict[str, Any]]:
    ANSWERS.clear()
    s1 = {
        "section_no": 1,
        "title": "Synthetic reading passage 1",
        "passages": [_passage(1)],
        "groups": [
            _group("tfng", [1, 2, 3, 4], ["TRUE", "FALSE", "NOT GIVEN", "TRUE"]),
            _group(
                "matching_headings",
                [5, 6, 7, 8, 9],
                ["iii", "i", "vii", "ii", "v"],
                options=_opts(ROMAN),
                config={"options_reusable": False},
            ),
            _group(
                "sentence_completion",
                [10, 11, 12, 13],
                ["harbour", "salt", "1890", "bridges"],
                config={"word_limit": 2, "allow_number": True},
            ),
        ],
    }
    s2 = {
        "section_no": 2,
        "title": "Synthetic reading passage 2",
        "passages": [_passage(2)],
        "groups": [
            _group("ynng", [14, 15, 16], ["YES", "NO", "NOT GIVEN"]),
            _group(
                "matching_information",
                [17, 18, 19, 20],
                ["B", "D", "A", "F"],
                options=_opts("ABCDEF"),
            ),
            _group("matching_features", [21, 22, 23], ["A", "C", "B"], options=_opts("ABC")),
            _group(
                "matching_sentence_endings", [24, 25, 26], ["D", "A", "E"], options=_opts("ABCDE")
            ),
        ],
    }
    multi = {
        "question_type": "mcq_multi",
        "instructions": "Choose TWO letters.",
        "options": _opts("ABCDE"),
        "questions": [
            {
                "number_from": 29,
                "number_to": 30,
                "answers": [{"value": "B"}, {"value": "E"}],
                "explanation": {"body": doc("Synthetic explanation 29-30.")},
            }
        ],
    }
    ANSWERS[29] = {"choices": ["B", "E"]}
    s3 = {
        "section_no": 3,
        "title": "Synthetic reading passage 3",
        "passages": [_passage(3)],
        "groups": [
            {
                **_group("mcq_single", [27, 28], ["C", "A"]),
                "questions": [
                    {**_q(27, "C"), "options": _opts("ABCD")},
                    {**_q(28, "A"), "options": _opts("ABCD")},
                ],
            },
            multi,
            _group(
                "summary_completion",
                [31, 32, 33],
                ["canal", "trade", "winter"],
                config={"word_limit": 1},
            ),
            _group("note_completion", [34, 35], ["copper", "museum"], config={"word_limit": 1}),
            _group(
                "table_completion",
                [36, 37],
                ["wheat", "1920"],
                config={"word_limit": 1, "allow_number": True},
            ),
            _group("flowchart_completion", [38], ["filter"], config={"word_limit": 1}),
            _group("diagram_labelling", [39], ["valve"], config={"word_limit": 1}),
            _group("short_answer", [40], ["ferry"], config={"word_limit": 2}),
        ],
    }
    return copy.deepcopy([s1, s2, s3])
