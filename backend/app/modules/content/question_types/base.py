"""Question-type handler contract (docs/QUESTION_BANK_DESIGN.md §4).

Handlers work on plain DTOs (not ORM rows) so they are pure and testable. The exam engine treats
`question_type` as opaque and calls handlers through the registry.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from app.modules.content.enums import IssueSeverity


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: IssueSeverity
    code: str
    location: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.severity is IssueSeverity.ERROR


def error(code: str, location: str, message: str) -> ValidationIssue:
    return ValidationIssue(IssueSeverity.ERROR, code, location, message)


def warning(code: str, location: str, message: str) -> ValidationIssue:
    return ValidationIssue(IssueSeverity.WARNING, code, location, message)


@dataclass(frozen=True, slots=True)
class OptionDTO:
    label: str
    text: str


@dataclass(frozen=True, slots=True)
class KeyDTO:
    slot: int
    canonical_value: str
    match_mode: str
    variants: tuple[str, ...] = ()

    @property
    def accepted(self) -> tuple[str, ...]:
        return (self.canonical_value, *self.variants)


@dataclass(frozen=True, slots=True)
class QuestionDTO:
    number_from: int
    number_to: int
    marks: int
    stem: dict[str, Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    options: tuple[OptionDTO, ...] = ()
    keys: tuple[KeyDTO, ...] = ()
    id: uuid.UUID | None = None

    @property
    def label(self) -> str:
        if self.number_from == self.number_to:
            return f"Q{self.number_from}"
        return f"Q{self.number_from}-{self.number_to}"


@dataclass(frozen=True, slots=True)
class GroupDTO:
    question_type: str
    config: dict[str, Any] = field(default_factory=dict)
    instructions: str | None = None
    options: tuple[OptionDTO, ...] = ()
    questions: tuple[QuestionDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoreOutcome:
    marks_awarded: int
    marks_available: int
    is_correct: bool
    reason: str  # stable code, e.g. "correct", "incorrect", "over_word_limit", "no_response"


class ResponseError(ValueError):
    """The response does not match the type's schema (maps to HTTP 422 in the exam engine)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class QuestionTypeHandler(ABC):
    code: str
    family: ClassVar[str]
    version: ClassVar[str] = "1.0.0"  # bump when scoring semantics change (scorer_version)

    @abstractmethod
    def validate_authoring(self, group: GroupDTO, location: str) -> list[ValidationIssue]:
        """Authoring-time checks: config, options, keys, numbering inside the group."""

    @abstractmethod
    def score(self, group: GroupDTO, question: QuestionDTO, response: Any) -> ScoreOutcome:
        """Score one question. `response` is the raw JSON stored for the answer (or None)."""

    @abstractmethod
    def student_view(self, group: GroupDTO) -> dict[str, Any]:
        """Student-facing representation. Must never contain keys, variants or explanations."""


def config_issues(
    model: type[BaseModel], config: dict[str, Any], location: str
) -> tuple[BaseModel | None, list[ValidationIssue]]:
    """Validate a group's config against the handler's Pydantic model."""
    try:
        return model.model_validate(config), []
    except ValidationError as exc:
        return None, [
            error(
                "group_config_invalid",
                f"{location} > config.{'.'.join(str(p) for p in e['loc'])}",
                e["msg"],
            )
            for e in exc.errors()
        ]
