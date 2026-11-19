"""API shapes of an AI evaluation (Writing and Speaking share them)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class CriterionOut(BaseModel):
    code: str
    name: str
    band: float
    rationale: str
    strengths: list[str]
    improvements: list[str]


class FeedbackOut(BaseModel):
    kind: str
    excerpt: str
    suggestion: str
    explanation: str


class EvaluationOut(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed", "unavailable", "rejected_input"]
    message: str | None
    band_overall: float | None
    criteria: list[CriterionOut]
    feedback: list[FeedbackOut]
    summary: str | None
    off_topic: bool
    improvement_plan: list[str] = []
    not_assessed: list[str]
    provider: str | None
    model: str | None
    prompt_version: str | None
    retryable: bool
    created_at: datetime
    finished_at: datetime | None


class ModelAnswerOut(BaseModel):
    band: float | None
    body: str
    author_note: str | None


def evaluation_out(e: Any, names: dict[str, str], retryable: bool) -> EvaluationOut:
    result = e.result or {}
    return EvaluationOut(
        id=e.id,
        status=e.status,
        message=e.error_message,
        band_overall=float(e.band_overall) if e.band_overall is not None else None,
        criteria=[
            CriterionOut(
                code=c["code"],
                name=names.get(c["code"], c["code"]),
                band=c["band"],
                rationale=c["rationale"],
                strengths=c.get("strengths", []),
                improvements=c.get("improvements", []),
            )
            for c in result.get("criteria", [])
        ],
        feedback=[FeedbackOut(**f) for f in result.get("feedback", [])],
        summary=result.get("summary"),
        off_topic=bool(result.get("off_topic", False)),
        improvement_plan=list(result.get("improvement_plan", [])),
        not_assessed=list(result.get("not_assessed", [])),
        provider=e.provider,
        model=e.model,
        prompt_version=e.prompt_version,
        retryable=retryable,
        created_at=e.created_at,
        finished_at=e.finished_at,
    )
