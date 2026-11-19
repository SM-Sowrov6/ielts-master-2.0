"""Which modules each question type belongs to (docs/QUESTION_BANK_DESIGN.md §3).

Migration 0004 seeds the same data into `question_types` (migrations keep their own frozen copy);
`tests/test_question_types.py` asserts both stay identical.
"""

_LR = frozenset({"listening", "reading"})
_R = frozenset({"reading"})
_L = frozenset({"listening"})

TYPE_MODULES: dict[str, frozenset[str]] = {
    "mcq_single": _LR,
    "mcq_multi": _LR,
    "tfng": _R,
    "ynng": _R,
    "matching_headings": _R,
    "matching_information": _R,
    "matching_features": _LR,
    "matching_sentence_endings": _R,
    "sentence_completion": _LR,
    "summary_completion": _LR,
    "note_completion": _LR,
    "table_completion": _LR,
    "flowchart_completion": _LR,
    "form_completion": _L,
    "diagram_labelling": _LR,
    "map_labelling": _L,
    "plan_labelling": _L,
    "short_answer": _LR,
}
