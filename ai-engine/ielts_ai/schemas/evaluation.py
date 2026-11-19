"""Structured evaluation output (validated Pydantic; the model's JSON is never trusted as-is).

Bands are half steps 0-9. The overall band is computed in code from the criterion bands
(`overall_band`), never taken from the model. Descriptor text comes from the platform's own,
admin-authored rubric versions (no copyrighted IELTS band descriptors are bundled).
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FeedbackKind = Literal[
    "grammar", "vocabulary", "spelling", "punctuation", "cohesion", "task", "fluency"
]


def _half_step(value: float) -> float:
    if not 0 <= value <= 9 or round(value * 2) != value * 2:
        raise ValueError("bands are half steps between 0 and 9")
    return value


class CriterionAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=2, max_length=8)
    band: float
    rationale: str = Field(min_length=1, max_length=1500)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    improvements: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("band")
    @classmethod
    def _band(cls, value: float) -> float:
        return _half_step(value)


class FeedbackItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FeedbackKind
    excerpt: str = Field(min_length=1, max_length=300)  # must occur verbatim in the response
    suggestion: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1, max_length=600)


class ModelAssessment(BaseModel):
    """What the LLM must return (JSON schema derived from this model)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria: list[CriterionAssessment] = Field(min_length=1, max_length=4)
    feedback: list[FeedbackItem] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=1500)
    off_topic: bool = False
    # Concrete next steps for the candidate (vocabulary, grammar, fluency, pronunciation practice).
    improvement_plan: list[str] = Field(default_factory=list, max_length=8)


class Evaluation(BaseModel):
    """Final, platform-validated result stored on the evaluation row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria: list[CriterionAssessment]
    feedback: list[FeedbackItem]
    summary: str
    off_topic: bool
    improvement_plan: list[str] = Field(default_factory=list)
    overall_band: float | None  # None when a required criterion could not be assessed
    not_assessed: list[str] = Field(default_factory=list)  # e.g. ["PR"] without an assessor
    prompt_key: str
    prompt_version: str
    prompt_hash: str
    provider: str
    model: str


def overall_band(bands: list[float]) -> float:
    """Mean of criterion bands rounded to the nearest half band (.25 → .5, .75 → next whole)."""
    mean = Decimal(str(sum(bands))) / Decimal(len(bands))
    return float((mean * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2)
