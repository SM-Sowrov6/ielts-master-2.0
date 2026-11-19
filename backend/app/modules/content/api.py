"""Public interface of the content module for other modules (docs/SYSTEM_ARCHITECTURE.md §3.2).

Only published or archived versions are exposed; students never receive answer keys, accepted
variants or explanations through this interface (key-stripping is done by each type handler).
`content_overview` returns catalogue counts for the admin console (callers authorise access).
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content import authoring, delivery, media, productive, rubrics
from app.modules.content.authoring import (
    LISTENING_TYPES,
    BookCreateIn,
    ContentModule,
    CreateListeningTestIn,
    DuplicateIn,
    EditionCreateIn,
    LicenceIn,
    ListStatus,
    ObjectiveModule,
    SaveListeningDraftIn,
)
from app.modules.content.enums import Difficulty, ReviewDecision, VersionStatus
from app.modules.content.errors import ContentNotFoundError, MediaRejectedError
from app.modules.content.importer import SectionIn
from app.modules.content.overview import ContentOverview, content_overview
from app.modules.content.productive import (
    ProductiveModule,
    SaveProductiveDraftIn,
    SpeakingPartIn,
    WritingTaskIn,
)
from app.modules.content.question_types import get_handler
from app.modules.content.question_types.base import ValidationIssue
from app.modules.content.rubrics import RubricModule, SaveRubricIn
from app.modules.content.service import load_version_tree
from app.modules.content.tree import group_to_dto

# Admin authoring (Listening management). Callers authorise every call (content.* permissions).
__all__ = [
    "LISTENING_TYPES",
    "BookCreateIn",
    "ContentModule",
    "ContentNotFoundError",
    "ContentOverview",
    "CreateListeningTestIn",
    "Difficulty",
    "DuplicateIn",
    "EditionCreateIn",
    "LicenceIn",
    "ListStatus",
    "MediaRejectedError",
    "ObjectiveModule",
    "ProductiveModule",
    "ReviewDecision",
    "RubricModule",
    "SaveListeningDraftIn",
    "SaveProductiveDraftIn",
    "SaveRubricIn",
    "SectionIn",
    "SpeakingPartIn",
    "ValidationIssue",
    "WritingTaskIn",
    "authoring",
    "content_overview",
    "delivery",
    "get_student_view",
    "media",
    "productive",
    "rubrics",
]


async def get_student_view(session: AsyncSession, test_version_id: uuid.UUID) -> dict[str, Any]:
    """Key-stripped content of an immutable version (published, or archived for history)."""
    version = await load_version_tree(session, test_version_id)
    if version.status not in (VersionStatus.PUBLISHED, VersionStatus.ARCHIVED):
        raise ContentNotFoundError(f"Test version {test_version_id} is not published.")
    return {
        "test_version_id": str(version.id),
        "version_no": version.version_no,
        "modules": [
            {
                "module": module.module,
                "variant": module.variant,
                "duration_seconds": module.duration_seconds,
                "sections": [
                    {
                        "section_no": section.section_no,
                        "title": section.title,
                        "instructions": section.instructions,
                        "has_audio": section.audio_asset_id is not None,
                        "passages": [
                            {
                                "title": passage.title,
                                "body": passage.body,
                                "paragraphs": [
                                    {"label": p.label, "text": p.plain_text}
                                    for p in passage.paragraphs
                                ],
                            }
                            for passage in section.passages
                        ],
                        "groups": [
                            get_handler(group.question_type).student_view(group_to_dto(group))
                            for group in section.groups
                        ],
                    }
                    for section in module.sections
                ],
                "writing_tasks": [
                    {"task_no": t.task_no, "prompt": t.prompt, "min_words": t.min_words}
                    for t in module.writing_tasks
                ],
                # Speaking questions are for the examiner; students only see Part 2 cue cards.
                "speaking_parts": [
                    {"part_no": p.part_no, "topic": p.topic, "cue_card": p.cue_card}
                    for p in module.speaking_parts
                ],
            }
            for module in version.modules
        ],
    }
