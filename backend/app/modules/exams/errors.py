"""Exam-engine errors with stable problem codes (docs/API_SPECIFICATION.md §4)."""

from typing import Any, ClassVar

from app.core.errors import DomainError


class AttemptNotFoundError(DomainError):
    """Also used for attempts owned by someone else (no existence leak, SECURITY §4.2)."""

    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "attempt_not_found"
    title: ClassVar[str] = "Attempt not found"


class TestUnavailableError(DomainError):
    __test__ = False
    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "test_unavailable"
    title: ClassVar[str] = "This test is not available"


class EntitlementRequiredError(DomainError):
    status_code: ClassVar[int] = 403
    code: ClassVar[str] = "entitlement_required"
    title: ClassVar[str] = "This test needs a plan that is not available yet"


class ModeNotAllowedError(DomainError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "mode_not_allowed"
    title: ClassVar[str] = "This mode is not available for this test"


class OpenExamAttemptExistsError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "attempt_open_exists"
    title: ClassVar[str] = "You already have an unfinished exam-mode attempt for this test"

    def __init__(self, attempt_id: str) -> None:
        super().__init__()
        self.attempt_id = attempt_id

    def extensions(self) -> dict[str, Any]:
        return {"attempt_id": self.attempt_id}


class AttemptStateError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "attempt_invalid_state"
    title: ClassVar[str] = "This action is not possible in the attempt's current state"

    def __init__(self, state: str, detail: str | None = None) -> None:
        super().__init__(detail)
        self.state = state

    def extensions(self) -> dict[str, Any]:
        return {"attempt_status": self.state}


class AttemptSubmittedError(AttemptStateError):
    code: ClassVar[str] = "attempt_submitted"
    title: ClassVar[str] = "This attempt has been submitted; answers can no longer change"


class SupersededSessionError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "superseded_session"
    title: ClassVar[str] = "This attempt was continued on another device or tab"


class WriterTokenInvalidError(DomainError):
    status_code: ClassVar[int] = 403
    code: ClassVar[str] = "writer_token_invalid"
    title: ClassVar[str] = "This device is not allowed to change the attempt"


class DeadlinePassedError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "attempt_deadline_passed"
    title: ClassVar[str] = "Time is up for this attempt"


class QuestionNotInAttemptError(DomainError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "question_not_in_attempt"
    title: ClassVar[str] = "The question is not part of this attempt"


class ResponseInvalidError(DomainError):
    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "response_invalid"
    title: ClassVar[str] = "The answer has an invalid format"


class SubmitKeyConflictError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "attempt_already_submitted"
    title: ClassVar[str] = "This attempt was already submitted"


class AudioUnavailableError(DomainError):
    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "audio_unavailable"
    title: ClassVar[str] = "The recording is not available"
