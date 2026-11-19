"""RFC 9457 problem+json error foundation (docs/API_SPECIFICATION.md §1).

Domain code raises `DomainError` subclasses with a stable `code`; handlers map every error to
`application/problem+json`. Internal details (stack traces, exception text) are never returned.
"""

from typing import Any, ClassVar, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:ielts-master:problem:"

log = structlog.get_logger("app.errors")


class DomainError(Exception):
    """Base class for expected business-rule failures. Subclass per error with a stable code."""

    status_code: ClassVar[int] = 400
    code: ClassVar[str] = "domain_error"
    title: ClassVar[str] = "Request could not be processed"

    def __init__(self, detail: str | None = None, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.headers = headers  # extra response headers, e.g. Retry-After on 429

    def extensions(self) -> dict[str, Any]:
        """Extra RFC 9457 members for this problem (must contain no internal details)."""
        return {}


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{PROBLEM_TYPE_PREFIX}{code}",
        "title": title,
        "status": status,
        "code": code,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    if errors is not None:
        body["errors"] = errors
    for key, value in (extensions or {}).items():
        body.setdefault(key, value)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)


async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    err = cast(DomainError, exc)  # handler is registered only for this type
    response = problem_response(
        request,
        status=err.status_code,
        code=err.code,
        title=err.title,
        detail=err.detail,
        extensions=err.extensions(),
    )
    if err.headers:
        response.headers.update(err.headers)
    return response


async def _http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    err = cast(StarletteHTTPException, exc)  # handler is registered only for this type
    code = {404: "not_found", 405: "method_not_allowed"}.get(err.status_code, "http_error")
    detail = err.detail if isinstance(err.detail, str) else None
    response = problem_response(
        request, status=err.status_code, code=code, title=detail or "HTTP error"
    )
    if err.headers:
        response.headers.update(err.headers)
    return response


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    err = cast(RequestValidationError, exc)  # handler is registered only for this type
    errors = [
        {
            "loc": list(item.get("loc", ())),
            "msg": item.get("msg", ""),
            "code": item.get("type", ""),
        }
        for item in err.errors()
    ]
    return problem_response(
        request,
        status=422,
        code="validation_error",
        title="Request validation failed",
        errors=errors,
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("request.unhandled_error", exc_type=type(exc).__name__)
    return problem_response(
        request, status=500, code="internal_error", title="Internal server error"
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
