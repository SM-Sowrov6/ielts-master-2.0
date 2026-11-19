"""Writing errors with stable problem codes."""

from typing import ClassVar

from app.core.errors import DomainError


class SubmissionNotFoundError(DomainError):
    """Also used for another user's submission (no existence leak)."""

    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "submission_not_found"
    title: ClassVar[str] = "Submission not found"


class WritingTestUnavailableError(DomainError):
    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "test_unavailable"
    title: ClassVar[str] = "This test is not available"


class SubmissionLockedError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "submission_locked"
    title: ClassVar[str] = "This response has been submitted and can no longer change"


class StaleRevisionError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "stale_revision"
    title: ClassVar[str] = "A newer version of this draft was saved from another tab or device"


class EvaluationNotRetryableError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "evaluation_not_retryable"
    title: ClassVar[str] = "This evaluation can only be retried after it failed or was unavailable"
