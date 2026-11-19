"""Synthetic content for tests ONLY. Every text is invented placeholder material; nothing here is
real IELTS content, and none of it may be loaded into a production database (D-04).

`synthetic_payload()` returns a complete Academic test in the import format:
Listening (4 sections x 10 questions), Reading (3 sections, 40 questions), Writing (2 tasks),
Speaking (3 parts), using a spread of question-type families.
"""

import copy
from typing import Any


def doc(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _text_question(number: int, answer: str) -> dict[str, Any]:
    return {
        "number_from": number,
        "answers": [{"value": answer}],
        "explanation": {"body": doc(f"Synthetic explanation for question {number}.")},
    }


def _listening_section(section_no: int, audio_asset_id: str | None) -> dict[str, Any]:
    start = (section_no - 1) * 10 + 1
    section: dict[str, Any] = {
        "section_no": section_no,
        "title": f"Synthetic listening part {section_no}",
        "groups": [
            {
                "question_type": "note_completion",
                "instructions": "Write NO MORE THAN TWO WORDS AND/OR A NUMBER for each answer.",
                "config": {"word_limit": 2, "allow_number": True},
                "questions": [
                    _text_question(
                        start + i, ["(the) library", "colour/color", "25", "zebra", "lamp"][i]
                    )
                    for i in range(5)
                ],
            },
            {
                "question_type": "mcq_single",
                "instructions": "Choose the correct letter, A, B or C.",
                "questions": [
                    {
                        "number_from": start + 5 + i,
                        "options": [
                            {"label": "A", "text": "Synthetic option A"},
                            {"label": "B", "text": "Synthetic option B"},
                            {"label": "C", "text": "Synthetic option C"},
                        ],
                        "answers": [{"value": "B"}],
                        "explanation": {"body": doc("Synthetic explanation.")},
                    }
                    for i in range(3)
                ],
            },
            {
                "question_type": "mcq_multi",
                "instructions": "Choose TWO letters, A-E.",
                "options": [
                    {"label": letter, "text": f"Synthetic choice {letter}"} for letter in "ABCDE"
                ],
                "questions": [
                    {
                        "number_from": start + 8,
                        "number_to": start + 9,
                        "answers": [{"value": "A"}, {"value": "D"}],
                        "explanation": {"body": doc("Synthetic explanation.")},
                    }
                ],
            },
        ],
    }
    if audio_asset_id is not None:
        section["audio_asset_id"] = audio_asset_id
    return section


def _reading_section(section_no: int) -> dict[str, Any]:
    start = (section_no - 1) * 13 + 1
    count = 14 if section_no == 3 else 13  # 13 + 13 + 14 = 40
    labels = ["A", "B", "C", "D", "E"]
    groups: list[dict[str, Any]] = [
        {
            "question_type": "tfng",
            "instructions": "TRUE, FALSE or NOT GIVEN.",
            "questions": [
                {
                    "number_from": start + i,
                    "answers": [{"value": ["TRUE", "FALSE", "NOT GIVEN"][i % 3]}],
                    "explanation": {"body": doc("Synthetic."), "evidence_paragraph_label": "B"},
                }
                for i in range(5)
            ],
        },
        {
            "question_type": "matching_headings",
            "instructions": "Choose the correct heading for each paragraph.",
            "config": {"options_reusable": False},
            "options": [
                {"label": r, "text": f"Synthetic heading {r}"}
                for r in ["i", "ii", "iii", "iv", "v", "vi"]
            ],
            "questions": [
                {
                    "number_from": start + 5 + i,
                    "answers": [{"value": ["ii", "iv", "i", "vi"][i]}],
                    "explanation": {"body": doc("Synthetic.")},
                }
                for i in range(4)
            ],
        },
        {
            "question_type": "summary_completion",
            "instructions": "Choose the correct word from the box.",
            "config": {"answer_format": "option"},
            "options": [{"label": letter, "text": f"word {letter}"} for letter in labels],
            "questions": [
                {
                    "number_from": start + 9 + i,
                    "answers": [{"value": labels[i]}],
                    "explanation": {"body": doc("Synthetic.")},
                }
                for i in range(count - 9)
            ],
        },
    ]
    return {
        "section_no": section_no,
        "title": f"Synthetic reading passage {section_no}",
        "passages": [
            {
                "title": "A synthetic passage",
                "body": doc("Synthetic paragraph text used only for automated tests."),
                "paragraphs": [
                    {"label": label, "text": f"Synthetic paragraph {label}."} for label in labels
                ],
            }
        ],
        "groups": groups,
    }


def synthetic_payload(
    *, slug: str = "synthetic-book", test_code: str = "T1", audio_asset_ids: list[str] | None = None
) -> dict[str, Any]:
    audio = audio_asset_ids or [None, None, None, None]  # type: ignore[list-item]
    return copy.deepcopy(
        {
            "schema_version": 1,
            "catalog": {
                "book": {
                    "slug": slug,
                    "title": "Synthetic Practice Book (test data)",
                    "series": "Synthetic",
                },
                "edition": {"label": "1st", "publication_year": 2026, "variant": "academic"},
                "test": {"code": test_code, "title": f"Synthetic Test {test_code}"},
            },
            "change_note": "synthetic import",
            "modules": [
                {
                    "module": "listening",
                    "variant": "common",
                    "duration_seconds": 1800,
                    "sections": [_listening_section(n, audio[n - 1]) for n in range(1, 5)],
                },
                {
                    "module": "reading",
                    "variant": "academic",
                    "duration_seconds": 3600,
                    "sections": [_reading_section(n) for n in range(1, 4)],
                },
                {
                    "module": "writing",
                    "variant": "academic",
                    "writing_tasks": [
                        {
                            "task_no": 1,
                            "task_kind": "academic_report",
                            "prompt": doc("Synthetic chart task."),
                            "min_words": 150,
                        },
                        {
                            "task_no": 2,
                            "task_kind": "essay",
                            "prompt": doc("Synthetic essay task."),
                            "min_words": 250,
                        },
                    ],
                },
                {
                    "module": "speaking",
                    "variant": "common",
                    "speaking_parts": [
                        {
                            "part_no": 1,
                            "topic": "Synthetic topic",
                            "questions": [{"text": "Synthetic question?"}],
                        },
                        {
                            "part_no": 2,
                            "topic": "Synthetic cue",
                            "cue_card": {"prompt": "Describe a synthetic thing."},
                        },
                        {
                            "part_no": 3,
                            "topic": "Synthetic discussion",
                            "questions": [{"text": "Why synthetic?"}],
                        },
                    ],
                },
            ],
        }
    )
