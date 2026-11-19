"""Writing and Speaking evaluation workflows (provider-agnostic; ADR-003 pure library).

Each workflow: guard the input → build a delimited prompt from the versioned template and the
platform rubric → `generate_structured` (Pydantic-validated) → cross-check the output (criteria
must match the rubric exactly, excerpts must occur in the response) → compute the overall band in
code. Invalid model output raises `EvaluationOutputError`; nothing is ever invented.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ielts_ai.guardrails.input import check_response, sanitize, word_count, wrap
from ielts_ai.prompts.registry import PromptRegistry, PromptTemplate
from ielts_ai.providers.base import LLMMessage, LLMProvider, LLMRequest, PronunciationAssessor
from ielts_ai.schemas.evaluation import (
    CriterionAssessment,
    Evaluation,
    FeedbackItem,
    ModelAssessment,
    overall_band,
)

PROMPTS = PromptRegistry.from_directory(Path(__file__).resolve().parent.parent / "prompts")
PRONUNCIATION = "PR"


class EvaluationOutputError(ValueError):
    """The provider's structured output did not satisfy the platform's checks."""


@dataclass(frozen=True)
class RubricCriterion:
    code: str
    name: str
    description: str
    bands: Sequence[tuple[int, str]]  # (band, descriptor) written by the platform's admins


@dataclass(frozen=True)
class WritingTaskInput:
    task_no: int
    task_kind: str
    prompt_text: str
    min_words: int


@dataclass(frozen=True)
class SpokenAnswer:
    part_no: int
    question: str
    transcript: str
    duration_ms: int


def _rubric_text(criteria: Sequence[RubricCriterion]) -> str:
    lines = []
    for c in criteria:
        lines.append(f"[{c.code}] {c.name}: {c.description}")
        lines.extend(f"  band {band}: {text}" for band, text in sorted(c.bands, reverse=True))
    return "\n".join(lines)


def _schema_hint() -> str:
    return json.dumps(ModelAssessment.model_json_schema(), separators=(",", ":"))


def _check(
    result: ModelAssessment, codes: Sequence[str], corpus: str
) -> tuple[list[CriterionAssessment], list[FeedbackItem]]:
    got = [c.code for c in result.criteria]
    if sorted(got) != sorted(codes):
        raise EvaluationOutputError(f"criteria {got} do not match the rubric {list(codes)}")
    order = {code: i for i, code in enumerate(codes)}
    criteria = sorted(result.criteria, key=lambda c: order[c.code])
    # Feedback quoting text that is not in the response is dropped, never shown.
    feedback = [f for f in result.feedback if f.excerpt.strip() and f.excerpt in corpus]
    return criteria, feedback


async def _run(
    llm: LLMProvider,
    template: PromptTemplate,
    *,
    feature: str,
    correlation_id: str,
    user_content: str,
) -> ModelAssessment:
    request = LLMRequest(
        feature=feature,
        correlation_id=correlation_id,
        messages=(
            LLMMessage(role="system", content=template.body),
            LLMMessage(role="user", content=user_content),
        ),
        max_output_tokens=2500,
        temperature=0.0,
    )
    return await llm.generate_structured(request, ModelAssessment)


async def evaluate_writing(
    llm: LLMProvider,
    *,
    task: WritingTaskInput,
    response: str,
    rubric: Sequence[RubricCriterion],
    correlation_id: str,
    model_name: str,
) -> Evaluation:
    clean = check_response(response)
    template = PROMPTS.get("writing.evaluate")
    user = "\n\n".join(
        [
            f"Task {task.task_no} ({task.task_kind}); minimum {task.min_words} words.",
            "Task prompt:\n" + sanitize(task.prompt_text),
            "Rubric:\n" + _rubric_text(rubric),
            f"Word count (computed by the platform): {word_count(clean)}",
            "Return JSON matching this schema:\n" + _schema_hint(),
            wrap(clean),
        ]
    )
    result = await _run(
        llm, template, feature="writing_eval", correlation_id=correlation_id, user_content=user
    )
    codes = [c.code for c in rubric]
    criteria, feedback = _check(result, codes, clean)
    return Evaluation(
        criteria=criteria,
        feedback=feedback,
        summary=result.summary,
        off_topic=result.off_topic,
        improvement_plan=result.improvement_plan,
        overall_band=overall_band([c.band for c in criteria]),
        prompt_key=template.key,
        prompt_version=template.version,
        prompt_hash=template.content_hash,
        provider=llm.name,
        model=model_name,
    )


async def evaluate_speaking(
    llm: LLMProvider,
    *,
    answers: Sequence[SpokenAnswer],
    rubric: Sequence[RubricCriterion],
    correlation_id: str,
    model_name: str,
    pronunciation: PronunciationAssessor | None = None,
    pronunciation_band: float | None = None,
) -> Evaluation:
    """FC/LR/GRA from transcripts; PR only from an audio assessor's band (ADR-011)."""
    transcripts = "\n\n".join(
        f"Part {a.part_no} — Q: {sanitize(a.question)}\nA: {sanitize(a.transcript).strip()}"
        for a in answers
    )
    check_response(" ".join(a.transcript for a in answers))
    total_ms = sum(a.duration_ms for a in answers) or 1
    words = sum(word_count(a.transcript) for a in answers)
    metrics = f"Speaking time {total_ms // 1000}s, {words} words, {words * 60000 // total_ms} wpm."
    text_criteria = [c for c in rubric if c.code != PRONUNCIATION]
    template = PROMPTS.get("speaking.evaluate")
    user = "\n\n".join(
        [
            "Rubric:\n" + _rubric_text(text_criteria),
            "Speech metrics (computed by the platform): " + metrics,
            "Return JSON matching this schema:\n" + _schema_hint(),
            wrap(transcripts),
        ]
    )
    result = await _run(
        llm, template, feature="speaking_eval", correlation_id=correlation_id, user_content=user
    )
    criteria, feedback = _check(result, [c.code for c in text_criteria], transcripts)
    not_assessed: list[str] = []
    if any(c.code == PRONUNCIATION for c in rubric):
        if pronunciation is not None and pronunciation_band is not None:
            criteria.append(
                CriterionAssessment(
                    code=PRONUNCIATION,
                    band=pronunciation_band,
                    rationale=f"Measured from audio by {pronunciation.name}.",
                )
            )
        else:
            not_assessed.append(PRONUNCIATION)
    return Evaluation(
        criteria=criteria,
        feedback=feedback,
        summary=result.summary,
        off_topic=result.off_topic,
        improvement_plan=result.improvement_plan,
        overall_band=None if not_assessed else overall_band([c.band for c in criteria]),
        not_assessed=not_assessed,
        prompt_key=template.key,
        prompt_version=template.version,
        prompt_hash=template.content_hash,
        provider=llm.name,
        model=model_name,
    )
