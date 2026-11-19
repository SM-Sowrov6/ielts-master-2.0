"""Content-domain enumerations. Stored as text + CHECK constraints (docs/DATABASE_SCHEMA.md §1)."""

from enum import StrEnum


class LicenceSource(StrEnum):
    ORIGINAL = "original"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    USER_GENERATED = "user_generated"


class PostLapseAccess(StrEnum):
    """What students may still see after a licence lapses (open decision D-14)."""

    KEEP_REVIEW = "keep_review"
    SCORES_ONLY = "scores_only"
    REMOVE = "remove"


class EditionVariant(StrEnum):
    ACADEMIC = "academic"
    GENERAL = "general"
    BOTH = "both"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ModuleKind(StrEnum):
    LISTENING = "listening"
    READING = "reading"
    WRITING = "writing"
    SPEAKING = "speaking"


class ModuleVariant(StrEnum):
    ACADEMIC = "academic"
    GENERAL = "general"
    COMMON = "common"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MatchMode(StrEnum):
    TEXT = "text"
    OPTION = "option"
    SET_MEMBER = "set_member"
    NUMERIC = "numeric"
    TIME = "time"
    DATE = "date"


class BodyFormat(StrEnum):
    PROSEMIRROR_JSON = "prosemirror_json"
    MARKDOWN = "markdown"


class WritingTaskKind(StrEnum):
    ACADEMIC_REPORT = "academic_report"
    GT_LETTER = "gt_letter"
    ESSAY = "essay"


class AssetKind(StrEnum):
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"


class AssetStatus(StrEnum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class ImportStatus(StrEnum):
    VALIDATED = "validated"
    FAILED = "failed"
    COMMITTED = "committed"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


def check_in(column: str, enum: type[StrEnum]) -> str:
    """SQL CHECK expression restricting a text column to an enum's values."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
