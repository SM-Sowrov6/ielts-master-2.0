"""Candidate Writing API schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.evaluation_schemas import EvaluationOut, ModelAnswerOut

_STRICT = ConfigDict(extra="forbid")


class WritingTestOut(BaseModel):
    test_id: uuid.UUID
    code: str
    title: str
    description: str | None
    difficulty: str | None
    tags: list[str]
    book_title: str
    edition_label: str
    published_at: datetime | None


class WritingTaskOut(BaseModel):
    task_no: int
    task_kind: str
    prompt_text: str
    min_words: int
    has_image: bool
    suggested_minutes: int


class SubmissionSummaryOut(BaseModel):
    id: uuid.UUID
    task_no: int
    status: Literal["draft", "submitted"]
    word_count: int
    updated_at: datetime
    submitted_at: datetime | None
    evaluation_status: str | None
    band_overall: float | None


class WritingTestDetailOut(BaseModel):
    test: WritingTestOut
    variant: str
    tasks: list[WritingTaskOut]
    submissions: list[SubmissionSummaryOut]


class StartIn(BaseModel):
    model_config = _STRICT
    test_id: uuid.UUID
    task_no: Literal[1, 2]


class SaveTextIn(BaseModel):
    model_config = _STRICT
    body: str = Field(max_length=20_000)
    client_revision: int = Field(ge=1)
    time_spent_seconds: int = Field(default=0, ge=0, le=6 * 3600)


class SubmissionOut(BaseModel):
    id: uuid.UUID
    test_id: uuid.UUID
    test_title: str
    task_no: int
    task: WritingTaskOut
    status: Literal["draft", "submitted"]
    body: str
    word_count: int
    client_revision: int
    time_spent_seconds: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    evaluation: EvaluationOut | None
    model_answers: list[ModelAnswerOut]


class ImageUrlOut(BaseModel):
    url: str
    expires_in_seconds: int
