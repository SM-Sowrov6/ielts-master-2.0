"""Candidate-facing schemas for Listening practice and attempts. Nothing here carries answer keys
except `ReviewItemOut`, which is served only for completed attempts of their owner."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")
Mode = Literal["practice", "exam"]
ExamModule = Literal["listening", "reading"]
Status = Literal["created", "in_progress", "submitted", "completed", "abandoned"]


class TestAttemptSummary(BaseModel):
    __test__ = False
    completed: int
    best_raw: int | None
    last_completed_at: datetime | None
    open_attempt_id: uuid.UUID | None
    open_attempt_mode: Mode | None


class ListeningTestOut(BaseModel):
    test_id: uuid.UUID
    code: str
    title: str
    description: str | None
    difficulty: Literal["easy", "medium", "hard"] | None
    tags: list[str]
    duration_seconds: int | None
    book_title: str
    edition_label: str
    locked: bool  # premium content needs plans (not available yet)
    sections: int
    questions: int
    published_at: datetime | None
    progress: TestAttemptSummary


class SectionSummaryOut(BaseModel):
    section_no: int
    title: str | None
    context: str | None
    questions: int
    number_from: int | None
    number_to: int | None
    question_types: list[str]
    has_audio: bool


class ModeRulesOut(BaseModel):
    mode: Mode
    timed: bool
    time_limit_seconds: int
    max_plays: int | None
    allow_seek: bool
    auto_submit: bool


class ListeningTestDetailOut(ListeningTestOut):
    section_list: list[SectionSummaryOut]
    modes: list[ModeRulesOut]
    default_mode: Mode
    attempts: list[AttemptOut]


class CreateAttemptIn(BaseModel):
    model_config = _STRICT
    test_id: uuid.UUID
    mode: Mode = "practice"
    module: ExamModule = "listening"


class AttemptTestOut(BaseModel):
    title: str
    code: str
    book_title: str | None = None


class AttemptOut(BaseModel):
    id: uuid.UUID
    module: ExamModule
    test_id: uuid.UUID
    mode: Mode
    status: Status
    test: AttemptTestOut
    started_at: datetime | None
    deadline_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None
    submitted_by: Literal["candidate", "deadline"] | None
    server_now: datetime
    writer_epoch: int
    questions_total: int
    answered: int | None = None
    raw_score: int | None = None
    max_score: int | None = None
    band_estimate: Decimal | None = None
    rules: dict[str, Any]


class LeaseOut(BaseModel):
    attempt: AttemptOut
    writer_epoch: int
    writer_token: str  # shown once; the server keeps only its hash


class AnswerItemIn(BaseModel):
    model_config = _STRICT
    question_id: uuid.UUID
    response: dict[str, Any] | None
    client_revision: int = Field(ge=1, le=2**62)
    flagged: bool = False


class SaveAnswersIn(BaseModel):
    model_config = _STRICT
    writer_epoch: int = Field(ge=1)
    answers: list[AnswerItemIn] = Field(min_length=1, max_length=50)


class StoredAnswerOut(BaseModel):
    question_id: uuid.UUID
    response: dict[str, Any] | None
    writer_epoch: int
    client_revision: int
    flagged: bool
    saved_at: datetime


class SaveAnswersOut(BaseModel):
    stored: list[StoredAnswerOut]
    server_now: datetime
    deadline_at: datetime | None


class AnswersOut(BaseModel):
    answers: list[StoredAnswerOut]
    server_now: datetime


class SubmitIn(BaseModel):
    model_config = _STRICT
    writer_epoch: int = Field(ge=0)
    final_answers: list[AnswerItemIn] = Field(default_factory=list, max_length=200)


class AudioOut(BaseModel):
    url: str
    expires_in_seconds: int
    offset_ms: int  # exam mode: resume point after a reload (0 = from the start)
    allow_seek: bool
    max_plays: int | None
    plays_used: int


class ImageOut(BaseModel):
    url: str
    expires_in_seconds: int


class BreakdownOut(BaseModel):
    marks: int
    max: int
    correct: int
    questions: int
    unanswered: int


class SectionBreakdownOut(BreakdownOut):
    section_no: int


class TypeBreakdownOut(BreakdownOut):
    question_type: str


class ResultOut(BaseModel):
    attempt: AttemptOut
    raw_score: int
    max_score: int
    percentage: float
    correct: int
    incorrect: int
    unanswered: int
    band_estimate: Decimal | None
    band_available: bool  # False until an approved conversion table exists
    sections: list[SectionBreakdownOut]
    question_types: list[TypeBreakdownOut]


class ReviewItemOut(BaseModel):
    question_id: uuid.UUID
    section_no: int
    question_type: str
    number_from: int
    number_to: int
    marks: int
    marks_awarded: int
    is_correct: bool
    reason: str
    response: dict[str, Any] | None
    accepted: list[list[str]]
    explanation: dict[str, Any] | None
    evidence_paragraph: str | None = None


class AttemptReviewOut(BaseModel):
    attempt: AttemptOut
    items: list[ReviewItemOut]
    content: dict[str, Any]  # the same key-stripped view used during the attempt


class HistoryOut(BaseModel):
    items: list[AttemptOut]
