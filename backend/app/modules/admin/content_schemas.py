"""Response/request schemas of the admin Listening-management API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.content.api import SectionIn, SpeakingPartIn, WritingTaskIn

_STRICT = ConfigDict(extra="forbid")


class IssueOut(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    location: str
    message: str


class ListeningRowOut(BaseModel):
    test_id: uuid.UUID
    version_id: uuid.UUID
    version_no: int
    code: str
    title: str
    book_title: str
    edition_label: str
    status: Literal["draft", "in_review", "approved", "published", "archived"]
    difficulty: Literal["easy", "medium", "hard"] | None
    sections: int
    questions: int
    duration_seconds: int | None
    updated_at: datetime
    created_by: uuid.UUID | None
    created_by_name: str | None
    live_version_id: uuid.UUID | None


class ListeningPageOut(BaseModel):
    items: list[ListeningRowOut]
    total: int
    offset: int
    limit: int


class ListeningOverviewOut(BaseModel):
    total: int
    draft: int
    in_review: int
    approved: int
    published: int
    archived: int


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: Literal["audio", "image", "document"]
    status: Literal["uploading", "processing", "ready", "failed"]
    mime_type: str
    size_bytes: int | None
    original_filename: str | None


class ReviewOut(BaseModel):
    reviewer_id: uuid.UUID
    reviewer_name: str | None
    decision: Literal["approved", "changes_requested"]
    comment: str | None
    created_at: datetime


class VersionSummaryOut(BaseModel):
    id: uuid.UUID
    version_no: int
    status: str
    updated_at: datetime


class VersionOut(BaseModel):
    id: uuid.UUID
    version_no: int
    status: Literal["draft", "in_review", "published", "archived"]
    approved: bool  # in review with a valid four-eyes approval since submission
    revision: datetime
    created_by: uuid.UUID | None
    created_by_name: str | None
    change_note: str | None
    description: str | None
    difficulty: Literal["easy", "medium", "hard"] | None
    tags: list[str]
    submitted_at: datetime | None
    published_at: datetime | None
    reviews: list[ReviewOut]


class TestOut(BaseModel):
    __test__ = False
    id: uuid.UUID
    code: str
    title: str
    admin_notes: str | None
    live_version_id: uuid.UUID | None


class CatalogRefOut(BaseModel):
    book_id: uuid.UUID
    book_title: str
    edition_id: uuid.UUID
    edition_label: str
    license_id: uuid.UUID


class EditorDocumentOut(BaseModel):
    test: TestOut
    catalog: CatalogRefOut
    version: VersionOut
    module: Literal["listening", "reading", "writing", "speaking"]
    variant: str
    duration_seconds: int | None
    sections: list[SectionIn]
    writing_tasks: list[WritingTaskIn] = []
    speaking_parts: list[SpeakingPartIn] = []
    assets: list[AssetOut]
    versions: list[VersionSummaryOut]


class SaveResultOut(BaseModel):
    document: EditorDocumentOut
    issues: list[IssueOut]  # what still blocks submission (publish strictness)


class IssuesOut(BaseModel):
    issues: list[IssueOut]
    ok: bool  # no errors at publish strictness


class ReviewIn(BaseModel):
    model_config = _STRICT
    decision: Literal["approved", "changes_requested"]
    comment: str | None = Field(default=None, max_length=2000)


class QuestionTypeOut(BaseModel):
    code: str
    family: str
    modules: list[str]


class LicenceOut(BaseModel):
    id: uuid.UUID
    source_type: str
    licensor: str
    licence_reference: str | None
    valid_from: Any | None
    valid_until: Any | None


class EditionOut(BaseModel):
    id: uuid.UUID
    label: str
    publication_year: int | None
    variant: str


class BookOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    license_id: uuid.UUID
    editions: list[EditionOut]


class MediaUploadIn(BaseModel):
    model_config = _STRICT
    test_id: uuid.UUID
    kind: Literal["audio", "image"]
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=100)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)


class MediaUploadOut(BaseModel):
    asset: AssetOut
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_in_seconds: int


class MediaUrlOut(BaseModel):
    asset: AssetOut
    url: str
    expires_in_seconds: int


class PreviewOut(BaseModel):
    """Admin preview: candidate view plus answers (admin-only route; never a student API)."""

    test_id: uuid.UUID
    version_id: uuid.UUID
    version_no: int
    status: str
    title: str
    code: str
    description: str | None
    difficulty: str | None
    duration_seconds: int | None
    module: str
    variant: str
    sections: list[dict[str, Any]]
    writing_tasks: list[dict[str, Any]] = []
    speaking_parts: list[dict[str, Any]] = []


class RubricBandOut(BaseModel):
    band: int
    descriptor: str


class RubricCriterionOut(BaseModel):
    code: str
    name: str
    description: str
    bands: list[RubricBandOut]


class RubricOut(BaseModel):
    id: uuid.UUID
    module: Literal["writing", "speaking"]
    version_no: int
    title: str
    status: Literal["draft", "in_review", "published", "archived"]
    approved: bool
    revision: datetime
    change_note: str | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    submitted_at: datetime | None
    published_at: datetime | None
    criteria: list[RubricCriterionOut]
    reviews: list[ReviewOut]
    issues: list[IssueOut]  # what still blocks submission


class CreateRubricIn(BaseModel):
    model_config = _STRICT
    module: Literal["writing", "speaking"]
