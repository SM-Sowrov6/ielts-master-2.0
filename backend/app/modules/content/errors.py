"""Content-domain errors with stable codes (mapped to problem+json by app.core.errors)."""

from typing import Any, ClassVar

from app.core.errors import DomainError
from app.modules.content.question_types.base import ValidationIssue


class ContentNotFoundError(DomainError):
    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "content_not_found"
    title: ClassVar[str] = "Content not found"


class InvalidTransitionError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "content_invalid_transition"
    title: ClassVar[str] = "This status change is not allowed"


class OpenDraftExistsError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "content_open_draft_exists"
    title: ClassVar[str] = "The test already has a draft or a version in review"


class SelfReviewError(DomainError):
    status_code: ClassVar[int] = 403
    code: ClassVar[str] = "content_self_review_forbidden"
    title: ClassVar[str] = "Authors cannot review their own version"


class ReviewRequiredError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "content_review_required"
    title: ClassVar[str] = "An approved review is required before publishing"


class CatalogConflictError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "content_catalog_conflict"
    title: ClassVar[str] = "Catalogue entry conflicts with existing data"


class ImportJobStateError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "import_job_invalid_state"
    title: ClassVar[str] = "The import job cannot be committed"


class ContentValidationError(DomainError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "content_validation_failed"
    title: ClassVar[str] = "Content failed validation"

    def __init__(self, issues: list[ValidationIssue]) -> None:
        errors = [i for i in issues if i.is_error]
        super().__init__(f"{len(errors)} validation error(s)")
        self.issues = issues

    def extensions(self) -> dict[str, Any]:
        return {
            "issues": [
                {
                    "severity": i.severity.value,
                    "code": i.code,
                    "location": i.location,
                    "message": i.message,
                }
                for i in self.issues
            ]
        }


class DraftConflictError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "content_draft_conflict"
    title: ClassVar[str] = "This draft was changed elsewhere. Reload it before saving again"


class ContentStateError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "content_invalid_state"
    title: ClassVar[str] = "This action is not possible in the content's current state"


class MediaRejectedError(DomainError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "media_rejected"
    title: ClassVar[str] = "The file was rejected"


class MediaStateError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "media_invalid_state"
    title: ClassVar[str] = "The media file is not in the expected state"


class MediaStorageUnavailableError(DomainError):
    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "media_storage_unavailable"
    title: ClassVar[str] = "Media storage is not available. Nothing was uploaded"


class MediaUploadsDisabledError(DomainError):
    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "media_uploads_disabled"
    title: ClassVar[str] = (
        "Media uploads are disabled in this environment until malware scanning exists"
    )
