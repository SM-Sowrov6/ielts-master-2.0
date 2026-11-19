"""Conversion of loaded ORM trees into handler DTOs, and eager-loading options for whole trees."""

from sqlalchemy.orm import selectinload
from sqlalchemy.orm.strategy_options import _AbstractLoad

from app.modules.content.models import (
    AnswerKey,
    Passage,
    Question,
    QuestionGroup,
    Section,
    SpeakingPart,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.modules.content.question_types.base import GroupDTO, KeyDTO, OptionDTO, QuestionDTO


def version_tree_options() -> list[_AbstractLoad]:
    """Load a full version tree in a fixed number of queries (relationships are lazy='raise')."""
    modules = selectinload(TestVersion.modules)
    sections = modules.selectinload(TestModule.sections)
    groups = sections.selectinload(Section.groups)
    questions = groups.selectinload(QuestionGroup.questions)
    return [
        selectinload(TestVersion.reviews),
        sections.selectinload(Section.audio),
        sections.selectinload(Section.passages).selectinload(Passage.paragraphs),
        groups.selectinload(QuestionGroup.options),
        questions.selectinload(Question.options),
        questions.selectinload(Question.answer_keys).selectinload(AnswerKey.variants),
        questions.selectinload(Question.explanation),
        modules.selectinload(TestModule.writing_tasks).selectinload(WritingTask.sample_answers),
        modules.selectinload(TestModule.speaking_parts).selectinload(SpeakingPart.questions),
        modules.selectinload(TestModule.speaking_parts).selectinload(SpeakingPart.sample_answers),
    ]


def group_to_dto(group: QuestionGroup) -> GroupDTO:
    return GroupDTO(
        question_type=group.question_type,
        config=dict(group.config or {}),
        instructions=group.instructions,
        options=tuple(OptionDTO(o.label, o.text) for o in group.options),
        questions=tuple(
            QuestionDTO(
                id=q.id,
                number_from=q.number_from,
                number_to=q.number_to,
                marks=q.marks,
                stem=q.stem,
                config=dict(q.config or {}),
                options=tuple(OptionDTO(o.label, o.text) for o in q.options),
                keys=tuple(
                    KeyDTO(
                        slot=k.slot,
                        canonical_value=k.canonical_value,
                        match_mode=k.match_mode,
                        variants=tuple(v.value for v in k.variants),
                    )
                    for k in q.answer_keys
                ),
            )
            for q in group.questions
        ),
    )
