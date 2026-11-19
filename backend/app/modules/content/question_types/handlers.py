"""Handler families for the 18 objective question types (docs/QUESTION_BANK_DESIGN.md §3-§6).

- OptionHandler:      one choice from an option list (MCQ single, T/F/NG, Y/N/NG, matching,
                      map labelling).
- MultiOptionHandler: "Choose N" multiple choice, one mark per correct choice.
- TextHandler:        completion / short answer; text, numeric, time or date keys. Types that may
                      use a word bank (`allow_option`) switch to option behaviour with
                      `answer_format: "option"`.
"""

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.content.enums import MatchMode
from app.modules.content.question_types.base import (
    GroupDTO,
    QuestionDTO,
    QuestionTypeHandler,
    ResponseError,
    ScoreOutcome,
    ValidationIssue,
    config_issues,
    error,
)
from app.modules.content.question_types.normalize import (
    TextRules,
    count_words,
    dates_equal,
    normalize_text,
    parse_date,
    parse_number,
    parse_time,
    times_equal,
)
from app.modules.content.richtext import validate_doc

_STRICT = ConfigDict(extra="forbid", frozen=True)


class OptionGroupConfig(BaseModel):
    model_config = _STRICT
    options_reusable: bool = True
    example: str | None = Field(default=None, max_length=500)


class TextGroupConfig(BaseModel):
    model_config = _STRICT
    answer_format: Literal["text", "option"] = "text"
    word_limit: int | None = Field(default=None, ge=1, le=5)
    allow_number: bool = False
    number_counts_as_word: bool = False
    case_sensitive: bool = False
    hyphen_policy: Literal["equivalent", "strict"] = "equivalent"
    british_american_equivalent: bool = True
    numbers_as_digits_or_words: bool = True
    options_reusable: bool = True
    template: dict[str, Any] | None = None

    def text_rules(self) -> TextRules:
        return TextRules(
            case_sensitive=self.case_sensitive,
            hyphen_policy=self.hyphen_policy,
            british_american_equivalent=self.british_american_equivalent,
            numbers_as_digits_or_words=self.numbers_as_digits_or_words,
        )

    @property
    def numbers_count_as_words(self) -> bool:
        return not self.allow_number or self.number_counts_as_word


class ChoiceResponse(BaseModel):
    model_config = _STRICT
    choice: str = Field(min_length=1, max_length=20)


class ChoicesResponse(BaseModel):
    model_config = _STRICT
    choices: list[str] = Field(min_length=1, max_length=10)


class TextResponse(BaseModel):
    model_config = _STRICT
    text: str = Field(max_length=200)


def _parse[T: BaseModel](model: type[T], raw: Any) -> T:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ResponseError("response_invalid", str(exc.errors()[0]["msg"])) from exc


def _fold(value: str) -> str:
    return " ".join(value.split()).casefold()


# ---------------------------------------------------------------------------------- shared
def _option_labels(
    group: GroupDTO, question: QuestionDTO, fixed: tuple[str, ...] | None
) -> list[str]:
    if fixed is not None:
        return list(fixed)
    return [o.label for o in (*group.options, *question.options)]


def _validate_option_questions(
    group: GroupDTO,
    location: str,
    *,
    fixed: tuple[str, ...] | None,
    options_reusable: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    labels_group = [_fold(o.label) for o in group.options]
    if len(labels_group) != len(set(labels_group)):
        issues.append(error("option_label_duplicate", location, "Option labels must be unique."))
    used: list[str] = []
    for question in group.questions:
        where = f"{location} > {question.label}"
        labels = [_fold(label) for label in _option_labels(group, question, fixed)]
        if not labels:
            issues.append(error("options_missing", where, "No options to choose from."))
        if question.number_from != question.number_to:
            issues.append(
                error("single_number_required", where, "This type uses one number per question.")
            )
        if len(question.keys) != 1 or question.keys[0].slot != 1:
            issues.append(error("key_count", where, "Exactly one answer key (slot 1) is required."))
            continue
        key = question.keys[0]
        if key.match_mode != MatchMode.OPTION:
            issues.append(
                error("key_match_mode", where, "Answer keys must use match mode 'option'.")
            )
        if _fold(key.canonical_value) not in labels:
            issues.append(
                error(
                    "key_not_an_option",
                    where,
                    f"Answer {key.canonical_value!r} is not one of the options.",
                )
            )
        used.append(_fold(key.canonical_value))
    if not options_reusable and len(used) != len(set(used)):
        issues.append(
            error(
                "option_reused",
                location,
                "options_reusable is false but two questions share the same answer.",
            )
        )
    return issues


def _score_option(
    group: GroupDTO, question: QuestionDTO, response: Any, fixed: tuple[str, ...] | None
) -> ScoreOutcome:
    if response is None:
        return ScoreOutcome(0, question.marks, False, "no_response")
    choice = _fold(_parse(ChoiceResponse, response).choice)
    if choice not in {_fold(label) for label in _option_labels(group, question, fixed)}:
        raise ResponseError("unknown_option", f"{choice!r} is not an option for this question.")
    correct = choice in {_fold(answer) for answer in question.keys[0].accepted}
    return ScoreOutcome(
        question.marks if correct else 0,
        question.marks,
        correct,
        "correct" if correct else "incorrect",
    )


def _options_view(options: tuple[Any, ...]) -> list[dict[str, str]]:
    return [{"label": o.label, "text": o.text} for o in options]


def _questions_view(group: GroupDTO, *, with_options: bool) -> list[dict[str, Any]]:
    return [
        {
            # Stable within an immutable version; answers are saved against it. Not a secret.
            "id": str(q.id) if q.id else None,
            "number_from": q.number_from,
            "number_to": q.number_to,
            "marks": q.marks,
            "stem": q.stem,
            **({"options": _options_view(q.options)} if with_options else {}),
        }
        for q in group.questions
    ]


# ---------------------------------------------------------------------------------- handlers
class OptionHandler(QuestionTypeHandler):
    family: ClassVar[str] = "option"

    def __init__(self, code: str, fixed_choices: tuple[str, ...] | None = None) -> None:
        self.code = code
        self.fixed_choices = fixed_choices

    def validate_authoring(self, group: GroupDTO, location: str) -> list[ValidationIssue]:
        config, issues = config_issues(OptionGroupConfig, group.config, location)
        reusable = config.options_reusable if isinstance(config, OptionGroupConfig) else True
        if self.fixed_choices is not None and (
            group.options or any(q.options for q in group.questions)
        ):
            issues.append(
                error(
                    "options_not_allowed",
                    location,
                    f"{self.code} uses the fixed choices {', '.join(self.fixed_choices)}.",
                )
            )
        return issues + _validate_option_questions(
            group, location, fixed=self.fixed_choices, options_reusable=reusable
        )

    def score(self, group: GroupDTO, question: QuestionDTO, response: Any) -> ScoreOutcome:
        return _score_option(group, question, response, self.fixed_choices)

    def student_view(self, group: GroupDTO) -> dict[str, Any]:
        config = OptionGroupConfig.model_validate(group.config)
        options = (
            [{"label": c, "text": c} for c in self.fixed_choices]
            if self.fixed_choices is not None
            else _options_view(group.options)
        )
        return {
            "question_type": self.code,
            "instructions": group.instructions,
            "answer_format": "option",
            "config": config.model_dump(),
            "options": options,
            "questions": _questions_view(group, with_options=True),
        }


class MultiOptionHandler(QuestionTypeHandler):
    family: ClassVar[str] = "multi_option"

    def __init__(self, code: str) -> None:
        self.code = code

    def validate_authoring(self, group: GroupDTO, location: str) -> list[ValidationIssue]:
        _, issues = config_issues(OptionGroupConfig, group.config, location)
        for question in group.questions:
            where = f"{location} > {question.label}"
            labels = [_fold(label) for label in _option_labels(group, question, None)]
            keys = [_fold(k.canonical_value) for k in question.keys]
            if len(question.keys) != question.marks:
                issues.append(
                    error("key_count", where, f"Needs {question.marks} keys (one per mark).")
                )
            if sorted(k.slot for k in question.keys) != list(range(1, len(question.keys) + 1)):
                issues.append(error("key_slots", where, "Key slots must be 1..N without gaps."))
            if any(k.match_mode != MatchMode.SET_MEMBER for k in question.keys):
                issues.append(error("key_match_mode", where, "Keys must use 'set_member'."))
            if len(keys) != len(set(keys)):
                issues.append(error("key_duplicate", where, "Correct choices must be distinct."))
            if any(k not in labels for k in keys):
                issues.append(error("key_not_an_option", where, "Every key must be an option."))
            if len(labels) <= question.marks:
                issues.append(
                    error("too_few_options", where, "There must be more options than marks.")
                )
        return issues

    def score(self, group: GroupDTO, question: QuestionDTO, response: Any) -> ScoreOutcome:
        if response is None:
            return ScoreOutcome(0, question.marks, False, "no_response")
        choices = [_fold(c) for c in _parse(ChoicesResponse, response).choices]
        if len(choices) != len(set(choices)):
            raise ResponseError("duplicate_choice", "Each option may be chosen once.")
        if len(choices) > question.marks:
            raise ResponseError("too_many_choices", f"Choose at most {question.marks} options.")
        labels = {_fold(label) for label in _option_labels(group, question, None)}
        if any(choice not in labels for choice in choices):
            raise ResponseError("unknown_option", "A chosen option does not exist.")
        keys = {_fold(k.canonical_value) for k in question.keys}
        awarded = sum(1 for choice in choices if choice in keys)
        correct = awarded == question.marks
        return ScoreOutcome(
            awarded,
            question.marks,
            correct,
            "correct" if correct else "partial" if awarded else "incorrect",
        )

    def student_view(self, group: GroupDTO) -> dict[str, Any]:
        return {
            "question_type": self.code,
            "instructions": group.instructions,
            "answer_format": "options",
            "config": OptionGroupConfig.model_validate(group.config).model_dump(),
            "options": _options_view(group.options),
            "questions": _questions_view(group, with_options=True),
        }


class TextHandler(QuestionTypeHandler):
    family: ClassVar[str] = "text"

    def __init__(self, code: str, *, allow_option: bool = False) -> None:
        self.code = code
        self.allow_option = allow_option

    def _config(self, group: GroupDTO) -> TextGroupConfig:
        return TextGroupConfig.model_validate(group.config)

    def validate_authoring(self, group: GroupDTO, location: str) -> list[ValidationIssue]:
        parsed, issues = config_issues(TextGroupConfig, group.config, location)
        if not isinstance(parsed, TextGroupConfig):
            return issues
        config = parsed
        if config.answer_format == "option":
            if not self.allow_option:
                return [
                    *issues,
                    error(
                        "answer_format_invalid", location, f"{self.code} only accepts text answers."
                    ),
                ]
            return issues + _validate_option_questions(
                group, location, fixed=None, options_reusable=config.options_reusable
            )
        if config.template is not None:
            doc_errors, blanks = validate_doc(config.template, allow_blanks=True)
            issues += [error("template_invalid", f"{location} > template", e) for e in doc_errors]
            numbers = {q.number_from for q in group.questions}
            if not doc_errors and blanks != numbers:
                issues.append(
                    error(
                        "template_blanks_mismatch",
                        f"{location} > template",
                        f"Blanks {sorted(blanks)} must match question numbers {sorted(numbers)}.",
                    )
                )
        for question in group.questions:
            issues += self._validate_text_question(
                config, question, f"{location} > {question.label}"
            )
        return issues

    def _validate_text_question(
        self, config: TextGroupConfig, question: QuestionDTO, where: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if question.number_from != question.number_to:
            issues.append(error("single_number_required", where, "One number per gap."))
        if len(question.keys) != 1 or question.keys[0].slot != 1:
            return [
                *issues,
                error("key_count", where, "Exactly one answer key (slot 1) is required."),
            ]
        key = question.keys[0]
        mode = key.match_mode
        if mode not in (MatchMode.TEXT, MatchMode.NUMERIC, MatchMode.TIME, MatchMode.DATE):
            return [
                *issues,
                error("key_match_mode", where, f"Match mode {mode!r} is not valid here."),
            ]
        for answer in key.accepted:
            if mode == MatchMode.TEXT and config.word_limit is not None:
                words = count_words(answer, number_counts_as_word=config.numbers_count_as_words)
                if words > config.word_limit:
                    issues.append(
                        error(
                            "key_exceeds_word_limit",
                            where,
                            f"Accepted answer {answer!r} has {words} words; "
                            f"limit is {config.word_limit}.",
                        )
                    )
            parsers = {
                MatchMode.NUMERIC: parse_number,
                MatchMode.TIME: parse_time,
                MatchMode.DATE: parse_date,
            }
            parser = parsers.get(MatchMode(mode))
            if parser is not None and parser(answer) is None:
                issues.append(
                    error("key_unparseable", where, f"{answer!r} is not a valid {mode} answer.")
                )
        return issues

    def score(self, group: GroupDTO, question: QuestionDTO, response: Any) -> ScoreOutcome:
        config = self._config(group)
        if config.answer_format == "option":
            return _score_option(group, question, response, None)
        marks = question.marks
        if response is None:
            return ScoreOutcome(0, marks, False, "no_response")
        text = _parse(TextResponse, response).text
        if not text.strip():
            return ScoreOutcome(0, marks, False, "no_response")
        if config.word_limit is not None and (
            count_words(text, number_counts_as_word=config.numbers_count_as_words)
            > config.word_limit
        ):
            return ScoreOutcome(0, marks, False, "over_word_limit")
        key = question.keys[0]
        correct = self._matches(config, key.match_mode, key.accepted, text)
        return ScoreOutcome(
            marks if correct else 0, marks, correct, "correct" if correct else "incorrect"
        )

    @staticmethod
    def _matches(config: TextGroupConfig, mode: str, accepted: tuple[str, ...], text: str) -> bool:
        if mode == MatchMode.NUMERIC:
            value = parse_number(text)
            return value is not None and any(parse_number(a) == value for a in accepted)
        if mode == MatchMode.TIME:
            parsed_time = parse_time(text)
            return parsed_time is not None and any(
                (k := parse_time(a)) is not None and times_equal(k, parsed_time) for a in accepted
            )
        if mode == MatchMode.DATE:
            parsed_date = parse_date(text)
            return parsed_date is not None and any(
                (d := parse_date(a)) is not None and dates_equal(d, parsed_date) for a in accepted
            )
        rules = config.text_rules()
        normalised = normalize_text(text, rules)
        return normalised in {normalize_text(a, rules) for a in accepted}

    def student_view(self, group: GroupDTO) -> dict[str, Any]:
        config = self._config(group)
        is_option = config.answer_format == "option"
        return {
            "question_type": self.code,
            "instructions": group.instructions,
            "answer_format": config.answer_format,
            "config": {
                "word_limit": config.word_limit,
                "allow_number": config.allow_number,
                "options_reusable": config.options_reusable,
                "template": config.template,
            },
            "options": _options_view(group.options) if is_option else [],
            "questions": _questions_view(group, with_options=is_option),
        }
