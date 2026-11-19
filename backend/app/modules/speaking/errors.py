"""Speaking errors with stable problem codes."""

from typing import ClassVar

from app.core.errors import DomainError


class SessionNotFoundError(DomainError):
    """Also used for another user's session or recording (no existence leak)."""

    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "speaking_session_not_found"
    title: ClassVar[str] = "Speaking session not found"


class SpeakingTestUnavailableError(DomainError):
    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "test_unavailable"
    title: ClassVar[str] = "This test is not available"


class SessionLockedError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "speaking_session_locked"
    title: ClassVar[str] = "This session has been submitted and can no longer change"


class RecordingRejectedError(DomainError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "recording_rejected"
    title: ClassVar[str] = "The recording could not be verified"


class RecordingsIncompleteError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "recordings_incomplete"
    title: ClassVar[str] = "Record an answer to every question before submitting"


class RecordingStorageUnavailableError(DomainError):
    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "recording_storage_unavailable"
    title: ClassVar[str] = "Recording storage is not available right now"


class EvaluationNotRetryableError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "evaluation_not_retryable"
    title: ClassVar[str] = "This evaluation can only be retried after it failed or was unavailable"
