"""Synthetic Listening content for tests ONLY (invented placeholder text; never real IELTS
material, D-04). One full test (4 sections, 40 questions) that uses all 13 Listening types."""

import copy
import hashlib
from collections.abc import Sequence
from typing import Any

from content_fixtures import doc

LISTENING_TYPES = {
    "form_completion",
    "mcq_single",
    "short_answer",
    "map_labelling",
    "plan_labelling",
    "mcq_multi",
    "matching_features",
    "note_completion",
    "table_completion",
    "flowchart_completion",
    "summary_completion",
    "sentence_completion",
    "diagram_labelling",
}


def wav_bytes(seed: int = 0, size: int = 4096) -> bytes:
    """A RIFF/WAVE container with filler samples (passes the signature check)."""
    body = bytes((seed + i) % 251 for i in range(size))
    return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WAVE" + body


def png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes(range(200))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(number: int, answer: str) -> dict[str, Any]:
    return {
        "number_from": number,
        "stem": doc(f"Synthetic gap sentence {number} ____."),
        "answers": [{"value": answer}],
        "explanation": {"body": doc(f"Synthetic explanation {number}.")},
    }


def _choice(number: int, answer: str) -> dict[str, Any]:
    return {
        "number_from": number,
        "answers": [{"value": answer}],
        "explanation": {"body": doc(f"Synthetic explanation {number}.")},
    }


def _letters(text: str, letters: str) -> list[dict[str, str]]:
    return [{"label": c, "text": f"{text} {c}"} for c in letters]


def listening_sections(
    audio_ids: Sequence[str | None], image_id: str | None = None
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = [
        {
            "section_no": 1,
            "title": "Synthetic part 1",
            "instructions": "Synthetic instructions for part 1.",
            "context": "A synthetic everyday conversation.",
            "groups": [
                {
                    "question_type": "form_completion",
                    "instructions": "Write NO MORE THAN TWO WORDS AND/OR A NUMBER.",
                    "config": {"word_limit": 2, "allow_number": True},
                    "questions": [
                        _text(n, a)
                        for n, a in zip(
                            range(1, 6),
                            ["(the) library", "colour/color", "25", "zebra", "lamp"],
                            strict=True,
                        )
                    ],
                },
                {
                    "question_type": "mcq_single",
                    "instructions": "Choose the correct letter, A, B or C.",
                    "questions": [
                        {
                            **_choice(n, "B"),
                            "stem": doc(f"Synthetic question {n}?"),
                            "options": _letters("Synthetic option", "ABC"),
                        }
                        for n in range(6, 9)
                    ],
                },
                {
                    "question_type": "short_answer",
                    "instructions": "Write ONE WORD ONLY.",
                    "config": {"word_limit": 1},
                    "questions": [_text(9, "river"), _text(10, "garden")],
                },
            ],
        },
        {
            "section_no": 2,
            "title": "Synthetic part 2",
            "groups": [
                {
                    "question_type": "map_labelling",
                    "instructions": "Label the synthetic map. Choose A-F.",
                    "image_asset_id": image_id,
                    "options": _letters("Place", "ABCDEF"),
                    "questions": [
                        _choice(n, a) for n, a in zip(range(11, 15), "ACEF", strict=True)
                    ],
                },
                {
                    "question_type": "plan_labelling",
                    "instructions": "Label the synthetic plan. ONE WORD ONLY.",
                    "config": {"word_limit": 1},
                    "questions": [_text(15, "kitchen"), _text(16, "office")],
                },
                {
                    "question_type": "mcq_multi",
                    "instructions": "Choose TWO letters, A-E.",
                    "options": _letters("Synthetic choice", "ABCDE"),
                    "questions": [
                        {
                            "number_from": 17,
                            "number_to": 18,
                            "answers": [{"value": "A"}, {"value": "D"}],
                            "explanation": {"body": doc("Synthetic explanation 17-18.")},
                        }
                    ],
                },
                {
                    "question_type": "matching_features",
                    "instructions": "Match each synthetic person with a feature, A-C.",
                    "options": _letters("Feature", "ABC"),
                    "questions": [_choice(19, "C"), _choice(20, "A")],
                },
            ],
        },
        {
            "section_no": 3,
            "title": "Synthetic part 3",
            "groups": [
                {
                    "question_type": "note_completion",
                    "config": {"word_limit": 2},
                    "questions": [_text(21, "survey"), _text(22, "data"), _text(23, "graph")],
                },
                {
                    "question_type": "table_completion",
                    "config": {"word_limit": 2},
                    "questions": [_text(24, "monday"), _text(25, "budget"), _text(26, "report")],
                },
                {
                    "question_type": "flowchart_completion",
                    "config": {"word_limit": 1},
                    "questions": [_text(27, "sample"), _text(28, "result")],
                },
                {
                    "question_type": "summary_completion",
                    "instructions": "Complete the synthetic summary. Choose A-D.",
                    "config": {"answer_format": "option"},
                    "options": _letters("Word", "ABCD"),
                    "questions": [_choice(29, "B"), _choice(30, "D")],
                },
            ],
        },
        {
            "section_no": 4,
            "title": "Synthetic part 4",
            "groups": [
                {
                    "question_type": "sentence_completion",
                    "config": {"word_limit": 1},
                    "questions": [
                        _text(n, w)
                        for n, w in zip(
                            range(31, 37),
                            ["energy", "ocean", "wind", "solar", "cost", "policy"],
                            strict=True,
                        )
                    ],
                },
                {
                    "question_type": "diagram_labelling",
                    "config": {"word_limit": 1},
                    "questions": [
                        _text(n, w)
                        for n, w in zip(
                            range(37, 41), ["valve", "pipe", "pump", "tank"], strict=True
                        )
                    ],
                },
            ],
        },
    ]
    for section, audio in zip(sections, audio_ids, strict=True):
        if audio is not None:
            section["audio_asset_id"] = audio
    return copy.deepcopy(sections)
