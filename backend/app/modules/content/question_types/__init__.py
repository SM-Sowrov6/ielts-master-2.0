"""Question-type registry: stable code -> handler (docs/QUESTION_BANK_DESIGN.md §3-§4).

The codes here must match the `question_types` reference table (migration 0004); a test enforces it.
"""

from app.modules.content.question_types.base import QuestionTypeHandler
from app.modules.content.question_types.handlers import (
    MultiOptionHandler,
    OptionHandler,
    TextHandler,
)

_HANDLERS: tuple[QuestionTypeHandler, ...] = (
    OptionHandler("mcq_single"),
    MultiOptionHandler("mcq_multi"),
    OptionHandler("tfng", fixed_choices=("TRUE", "FALSE", "NOT GIVEN")),
    OptionHandler("ynng", fixed_choices=("YES", "NO", "NOT GIVEN")),
    OptionHandler("matching_headings"),
    OptionHandler("matching_information"),
    OptionHandler("matching_features"),
    OptionHandler("matching_sentence_endings"),
    TextHandler("sentence_completion"),
    TextHandler("summary_completion", allow_option=True),
    TextHandler("note_completion"),
    TextHandler("table_completion"),
    TextHandler("flowchart_completion", allow_option=True),
    TextHandler("form_completion"),
    TextHandler("diagram_labelling", allow_option=True),
    OptionHandler("map_labelling"),
    TextHandler("plan_labelling", allow_option=True),
    TextHandler("short_answer"),
)

REGISTRY: dict[str, QuestionTypeHandler] = {handler.code: handler for handler in _HANDLERS}


class UnknownQuestionTypeError(KeyError):
    pass


def get_handler(code: str) -> QuestionTypeHandler:
    try:
        return REGISTRY[code]
    except KeyError:
        raise UnknownQuestionTypeError(code) from None


__all__ = ["REGISTRY", "QuestionTypeHandler", "UnknownQuestionTypeError", "get_handler"]
