"""Content-domain ORM models (docs/DATABASE_SCHEMA.md §4, docs/CONTENT_MANAGEMENT_ARCHITECTURE.md).

Logical identity (licence → book → edition → test) is separate from versioned content
(test_version → modules → … → answer keys). Published/archived versions are immutable,
enforced by the service layer and by database triggers (migration 0005).

Actor columns (`created_by`, `published_by`, `reviewer_id`, `uploaded_by`) are plain UUIDs until
users exist (Phase 3b adds the foreign keys).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.orm import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.content.enums import (
    AssetKind,
    AssetStatus,
    BodyFormat,
    Difficulty,
    EditionVariant,
    ImportStatus,
    IssueSeverity,
    LicenceSource,
    MatchMode,
    ModuleKind,
    ModuleVariant,
    PostLapseAccess,
    ReviewDecision,
    VersionStatus,
    WritingTaskKind,
    check_in,
)

TREE = "all, delete-orphan"  # cascade inside one aggregate (a test version tree)


# --------------------------------------------------------------------------- licences & media
class ContentLicence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_licenses"
    __table_args__ = (
        CheckConstraint(check_in("source_type", LicenceSource), name="source_type"),
        CheckConstraint(
            f"post_lapse_access IS NULL OR {check_in('post_lapse_access', PostLapseAccess)}",
            name="post_lapse_access",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_from <= valid_until",
            name="validity_range",
        ),
    )

    source_type: Mapped[str] = mapped_column(String(20))
    licensor: Mapped[str] = mapped_column(String(200))
    licence_reference: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    # D-14 is open: no default is assumed; NULL means "not decided for this licence".
    post_lapse_access: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    def is_valid_on(self, day: date) -> bool:
        if self.valid_from is not None and day < self.valid_from:
            return False
        return self.valid_until is None or day <= self.valid_until


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata only in Phase 5a; the upload/processing pipeline arrives in Phase 5b."""

    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(check_in("kind", AssetKind), name="kind"),
        CheckConstraint(check_in("status", AssetStatus), name="status"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_non_negative"),
    )

    kind: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int | None]
    duration_ms: Mapped[int | None]
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), server_default=AssetStatus.UPLOADING.value)
    license_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_licenses.id", ondelete="RESTRICT")
    )
    original_filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID | None]
    licence: Mapped[ContentLicence] = relationship(lazy="raise")


# --------------------------------------------------------------------------- catalogue
class Book(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "books"
    __table_args__ = (
        Index("ix_books_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_books_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    series: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    license_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_licenses.id", ondelete="RESTRICT")
    )
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    is_premium: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(series, '') || ' ' "
            "|| coalesce(description, ''))",
            persisted=True,
        ),
    )

    licence: Mapped[ContentLicence] = relationship(lazy="raise")
    editions: Mapped[list[BookEdition]] = relationship(
        back_populates="book", order_by="BookEdition.sort_order", lazy="raise"
    )


class BookEdition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "book_editions"
    __table_args__ = (
        UniqueConstraint("book_id", "edition_label"),
        CheckConstraint(check_in("variant", EditionVariant), name="variant"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("books.id", ondelete="RESTRICT"))
    edition_label: Mapped[str] = mapped_column(String(100))
    publication_year: Mapped[int | None]
    variant: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    book: Mapped[Book] = relationship(back_populates="editions", lazy="raise")
    tests: Mapped[list[Test]] = relationship(
        back_populates="edition", order_by="Test.sort_order", lazy="raise"
    )


class Test(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __test__ = False  # not a pytest test class
    __tablename__ = "tests"
    __table_args__ = (UniqueConstraint("edition_id", "code"),)

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("book_editions.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    admin_notes: Mapped[str | None] = mapped_column(Text)  # internal; never in student views
    # Intentional FK cycle with test_versions.test_id; set only in the publish transaction.
    current_published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "test_versions.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_tests_current_published_version_id_test_versions",
        )
    )

    edition: Mapped[BookEdition] = relationship(back_populates="tests", lazy="raise")


# --------------------------------------------------------------------------- versioned tree
class TestVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __test__ = False  # not a pytest test class
    __tablename__ = "test_versions"
    __table_args__ = (
        UniqueConstraint("test_id", "version_no"),
        CheckConstraint(check_in("status", VersionStatus), name="status"),
        CheckConstraint("version_no >= 1", name="version_no_positive"),
        CheckConstraint(
            f"difficulty IS NULL OR {check_in('difficulty', Difficulty)}", name="difficulty"
        ),
        # At most one published version, and at most one open (draft/in_review) version per test.
        Index(
            "uq_test_versions_one_published",
            "test_id",
            unique=True,
            postgresql_where=sql_text("status = 'published'"),
        ),
        Index(
            "uq_test_versions_one_open",
            "test_id",
            unique=True,
            postgresql_where=sql_text("status IN ('draft', 'in_review')"),
        ),
    )

    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tests.id", ondelete="RESTRICT", name="fk_test_versions_test_id_tests")
    )
    version_no: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), server_default=VersionStatus.DRAFT.value)
    change_note: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str | None] = mapped_column(String(10))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), server_default="{}")
    created_by: Mapped[uuid.UUID | None]
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None]

    test: Mapped[Test] = relationship(foreign_keys=[test_id], lazy="raise")
    modules: Mapped[list[TestModule]] = relationship(
        back_populates="version", cascade=TREE, order_by="TestModule.sort_order", lazy="raise"
    )
    reviews: Mapped[list[ContentReview]] = relationship(
        cascade=TREE, order_by="ContentReview.created_at", lazy="raise"
    )


class TestModule(UUIDPrimaryKeyMixin, Base):
    __test__ = False  # not a pytest test class
    __tablename__ = "test_modules"
    __table_args__ = (
        UniqueConstraint("test_version_id", "module", "variant"),
        CheckConstraint(check_in("module", ModuleKind), name="module"),
        CheckConstraint(check_in("variant", ModuleVariant), name="variant"),
    )

    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="CASCADE")
    )
    module: Mapped[str] = mapped_column(String(20))
    variant: Mapped[str] = mapped_column(String(20))
    duration_seconds: Mapped[int | None]
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    version: Mapped[TestVersion] = relationship(back_populates="modules", lazy="raise")
    sections: Mapped[list[Section]] = relationship(
        cascade=TREE, order_by="Section.section_no", lazy="raise"
    )
    writing_tasks: Mapped[list[WritingTask]] = relationship(
        cascade=TREE, order_by="WritingTask.task_no", lazy="raise"
    )
    speaking_parts: Mapped[list[SpeakingPart]] = relationship(
        cascade=TREE, order_by="SpeakingPart.part_no", lazy="raise"
    )


class Section(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("test_module_id", "section_no"),)

    test_module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_modules.id", ondelete="CASCADE")
    )
    section_no: Mapped[int]
    title: Mapped[str | None] = mapped_column(String(300))
    instructions: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    audio_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT")
    )
    duration_seconds: Mapped[int | None]

    audio: Mapped[MediaAsset | None] = relationship(lazy="raise")
    passages: Mapped[list[Passage]] = relationship(
        cascade=TREE, order_by="Passage.sort_order", lazy="raise"
    )
    groups: Mapped[list[QuestionGroup]] = relationship(
        cascade=TREE, order_by="QuestionGroup.sort_order", lazy="raise"
    )


class Passage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "passages"
    __table_args__ = (CheckConstraint(check_in("body_format", BodyFormat), name="body_format"),)

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    title: Mapped[str | None] = mapped_column(String(300))
    body_format: Mapped[str] = mapped_column(
        String(20), server_default=BodyFormat.PROSEMIRROR_JSON.value
    )
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    word_count: Mapped[int | None]

    paragraphs: Mapped[list[Paragraph]] = relationship(
        cascade=TREE, order_by="Paragraph.sort_order", lazy="raise"
    )


class Paragraph(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "paragraphs"

    passage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("passages.id", ondelete="CASCADE"))
    label: Mapped[str | None] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    plain_text: Mapped[str] = mapped_column(Text)


class QuestionType(Base):
    """Reference table of supported question types (seeded; codes are stable, never renamed)."""

    __tablename__ = "question_types"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    family: Mapped[str] = mapped_column(String(30))
    modules: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    handler_version: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))


class QuestionGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "question_groups"

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    question_type: Mapped[str] = mapped_column(
        ForeignKey("question_types.code", ondelete="RESTRICT")
    )
    instructions: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    image_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT")
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    questions: Mapped[list[Question]] = relationship(
        cascade=TREE, order_by="Question.number_from", lazy="raise"
    )
    options: Mapped[list[QuestionOption]] = relationship(
        cascade=TREE,
        order_by="QuestionOption.sort_order",
        primaryjoin="QuestionGroup.id == QuestionOption.group_id",
        lazy="raise",
    )


class Question(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("number_from >= 1 AND number_from <= number_to", name="number_range"),
        # One mark per question number (IELTS); "Choose TWO" spanning 21-22 = 2 marks.
        CheckConstraint("marks = number_to - number_from + 1", name="marks_match_numbers"),
        CheckConstraint(
            f"difficulty IS NULL OR {check_in('difficulty', Difficulty)}", name="difficulty"
        ),
        Index("ix_questions_group_number", "group_id", "number_from"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_groups.id", ondelete="CASCADE")
    )
    lineage_id: Mapped[uuid.UUID] = mapped_column(index=True)
    number_from: Mapped[int]
    number_to: Mapped[int]
    marks: Mapped[int]
    stem: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    difficulty: Mapped[str | None] = mapped_column(String(10))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), server_default="{}")

    options: Mapped[list[QuestionOption]] = relationship(
        cascade=TREE,
        order_by="QuestionOption.sort_order",
        primaryjoin="Question.id == QuestionOption.question_id",
        lazy="raise",
    )
    answer_keys: Mapped[list[AnswerKey]] = relationship(
        cascade=TREE, order_by="AnswerKey.slot", lazy="raise"
    )
    explanation: Mapped[Explanation | None] = relationship(cascade=TREE, lazy="raise")


class QuestionOption(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "question_options"
    __table_args__ = (
        CheckConstraint("num_nonnulls(question_id, group_id) = 1", name="exactly_one_parent"),
    )

    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE")
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("question_groups.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class AnswerKey(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "answer_keys"
    __table_args__ = (
        UniqueConstraint("question_id", "slot"),
        CheckConstraint("slot >= 1", name="slot_positive"),
        CheckConstraint(check_in("match_mode", MatchMode), name="match_mode"),
    )

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    slot: Mapped[int]
    canonical_value: Mapped[str] = mapped_column(Text)
    # The authored key notation, e.g. "(the) library", kept for review and export.
    notation: Mapped[str | None] = mapped_column(Text)
    match_mode: Mapped[str] = mapped_column(String(20))

    variants: Mapped[list[AnswerVariant]] = relationship(
        cascade=TREE, order_by="AnswerVariant.value", lazy="raise"
    )


class AnswerVariant(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "answer_variants"
    __table_args__ = (UniqueConstraint("answer_key_id", "value"),)

    answer_key_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("answer_keys.id", ondelete="CASCADE")
    )
    value: Mapped[str] = mapped_column(Text)


class Explanation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "explanations"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True
    )
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_paragraph_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paragraphs.id", ondelete="SET NULL")
    )
    audio_start_ms: Mapped[int | None]
    audio_end_ms: Mapped[int | None]


class WritingTask(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "writing_tasks"
    __table_args__ = (
        CheckConstraint("task_no IN (1, 2)", name="task_no"),
        CheckConstraint(check_in("task_kind", WritingTaskKind), name="task_kind"),
        CheckConstraint("min_words > 0", name="min_words_positive"),
    )

    # NULL for standalone practice tasks (not part of a versioned test).
    test_module_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_modules.id", ondelete="CASCADE")
    )
    task_no: Mapped[int]
    task_kind: Mapped[str] = mapped_column(String(30))
    prompt: Mapped[dict[str, Any]] = mapped_column(JSONB)
    image_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT")
    )
    min_words: Mapped[int]
    key_features: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")

    sample_answers: Mapped[list[SampleAnswer]] = relationship(
        cascade=TREE, order_by="SampleAnswer.created_at", lazy="raise"
    )


class SpeakingPart(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "speaking_parts"
    __table_args__ = (
        UniqueConstraint("test_module_id", "part_no"),
        CheckConstraint("part_no IN (1, 2, 3)", name="part_no"),
    )

    test_module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_modules.id", ondelete="CASCADE")
    )
    part_no: Mapped[int]
    topic: Mapped[str] = mapped_column(String(300))
    cue_card: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    questions: Mapped[list[SpeakingQuestion]] = relationship(
        cascade=TREE, order_by="SpeakingQuestion.sort_order", lazy="raise"
    )
    sample_answers: Mapped[list[SampleAnswer]] = relationship(
        cascade=TREE, order_by="SampleAnswer.created_at", lazy="raise"
    )


class SpeakingQuestion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "speaking_questions"

    speaking_part_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("speaking_parts.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    is_follow_up: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))


class SampleAnswer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Shown only where the licence permits (FR-WR-10); always carries its own licence."""

    __tablename__ = "sample_answers"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(writing_task_id, speaking_part_id) = 1", name="exactly_one_target"
        ),
        CheckConstraint(
            "band IS NULL OR (band >= 0 AND band <= 9 AND band * 2 = floor(band * 2))",
            name="band_half_steps",
        ),
    )

    writing_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="CASCADE")
    )
    speaking_part_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("speaking_parts.id", ondelete="CASCADE")
    )
    band: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    body: Mapped[str] = mapped_column(Text)
    license_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_licenses.id", ondelete="RESTRICT")
    )
    author_note: Mapped[str | None] = mapped_column(Text)


class ContentReview(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "content_reviews"
    __table_args__ = (CheckConstraint(check_in("decision", ReviewDecision), name="decision"),)

    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="CASCADE")
    )
    reviewer_id: Mapped[uuid.UUID]
    decision: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()"), nullable=False
    )


# --------------------------------------------------------------------------- imports
class ImportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint(check_in("status", ImportStatus), name="status"),
        CheckConstraint("source_format IN ('json')", name="source_format"),
    )

    status: Mapped[str] = mapped_column(String(20))
    source_format: Mapped[str] = mapped_column(String(10), server_default="json")
    file_name: Mapped[str] = mapped_column(String(300))
    file_sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[uuid.UUID | None]
    license_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_licenses.id", ondelete="RESTRICT")
    )
    # Immutable snapshot of the validated payload; commit re-builds from it (never re-reads files).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    result_test_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_versions.id", ondelete="SET NULL")
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    issues: Mapped[list[ImportJobIssue]] = relationship(cascade=TREE, lazy="raise")


class ImportJobIssue(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_job_issues"
    __table_args__ = (CheckConstraint(check_in("severity", IssueSeverity), name="severity"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)


# --------------------------------------------------------------------------- band conversion
class BandConversionTable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structure only in Phase 5a: no values are seeded until a source is approved."""

    __tablename__ = "band_conversion_tables"
    __table_args__ = (
        CheckConstraint("module IN ('listening', 'reading')", name="module"),
        CheckConstraint(check_in("variant", ModuleVariant), name="variant"),
        Index(
            "uq_band_conversion_tables_one_default",
            "module",
            "variant",
            unique=True,
            postgresql_where=sql_text("is_default"),
        ),
    )

    module: Mapped[str] = mapped_column(String(20))
    variant: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))

    rows: Mapped[list[BandConversionRow]] = relationship(
        cascade=TREE, order_by="BandConversionRow.raw_min", lazy="raise"
    )


class BandConversionRow(Base):
    __tablename__ = "band_conversion_rows"
    __table_args__ = (
        CheckConstraint("raw_min >= 0 AND raw_min <= raw_max", name="raw_range"),
        CheckConstraint("band >= 0 AND band <= 9 AND band * 2 = floor(band * 2)", name="band"),
    )

    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("band_conversion_tables.id", ondelete="CASCADE"), primary_key=True
    )
    raw_min: Mapped[int] = mapped_column(primary_key=True)
    raw_max: Mapped[int]
    band: Mapped[Decimal] = mapped_column(Numeric(2, 1))


# --------------------------------------------------------------------------- rubrics
class RubricVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Platform-authored assessment criteria for Writing or Speaking (own wording; no copyrighted
    IELTS descriptors). Four-eyes reviewed; immutable once out of draft (database trigger)."""

    __tablename__ = "rubric_versions"
    __table_args__ = (
        CheckConstraint("module IN ('writing', 'speaking')", name="module"),
        CheckConstraint("status IN ('draft', 'in_review', 'published', 'archived')", name="status"),
        UniqueConstraint("module", "version_no"),
        Index(
            "uq_rubric_versions_one_published",
            "module",
            unique=True,
            postgresql_where=sql_text("status = 'published'"),
        ),
    )

    module: Mapped[str] = mapped_column(String(20))
    version_no: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    # [{code, name, description, bands: [{band, descriptor}]}]
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    status: Mapped[str] = mapped_column(String(20), server_default="draft")
    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None]
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None]

    reviews: Mapped[list[RubricReview]] = relationship(
        cascade=TREE, order_by="RubricReview.created_at", lazy="raise"
    )


class RubricReview(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rubric_reviews"
    __table_args__ = (CheckConstraint(check_in("decision", ReviewDecision), name="decision"),)

    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rubric_versions.id", ondelete="CASCADE")
    )
    reviewer_id: Mapped[uuid.UUID]
    decision: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()"), nullable=False
    )
