"""CSRF protection for every state-changing API request (SECURITY_GUIDELINES.md §3).

Applies to ALL unsafe methods under /api/, authenticated or not (login and registration CSRF
included). A request must pass every check:

1. Fetch metadata: `Sec-Fetch-Site`, when sent, must be `same-origin`.
2. `Origin`, when sent, must be the app origin (PUBLIC_APP_URL) or an explicitly trusted origin.
3. A request body must be `application/json` (HTML forms cannot send it cross-site without a
   CORS preflight, which this API never grants).
4. Signed double-submit token: header `X-CSRF-Token` equals the CSRF cookie, and its HMAC binds
   it to the current session cookie (or to "anonymous" before login). A token planted by a
   related subdomain or obtained for another session does not verify. Tokens are re-issued on
   login, logout and session rotation (`GET /api/v1/auth/csrf` issues one on demand).
"""

import hashlib
import hmac
import secrets

from fastapi import Response
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import problem_response
from app.modules.identity.sessions import cookie_names
from app.modules.identity.tokens import AuthKeys

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CSRF_HEADER = "x-csrf-token"


def session_binding(session_cookie: str | None) -> str:
    if not session_cookie:
        return "anonymous"
    return hashlib.sha256(session_cookie.encode("utf-8")).hexdigest()


def _signature(key: bytes, binding: str, nonce: str) -> str:
    return hmac.new(key, f"{binding}|{nonce}".encode(), hashlib.sha256).hexdigest()


def issue_token(keys: AuthKeys, session_cookie: str | None) -> str:
    nonce = secrets.token_urlsafe(18)
    return f"{nonce}.{_signature(keys.csrf, session_binding(session_cookie), nonce)}"


def token_is_valid(keys: AuthKeys, session_cookie: str | None, token: str) -> bool:
    nonce, _, signature = token.partition(".")
    if not nonce or not signature or len(token) > 200:
        return False
    expected = _signature(keys.csrf, session_binding(session_cookie), nonce)
    return hmac.compare_digest(expected, signature)


def set_csrf_cookie(response: Response, settings: Settings, token: str) -> None:
    # Readable by the page's JavaScript (it must echo it in a header); not a credential.
    response.set_cookie(
        cookie_names(settings).csrf,
        token,
        max_age=settings.session_absolute_ttl_seconds,
        path="/",
        secure=settings.cookie_secure_effective,
        httponly=False,
        samesite="lax",
    )


INTERNAL_PREFIX = "/api/v1/internal/"


class CsrfMiddleware:
    def __init__(self, app: ASGIApp, *, settings: Settings, keys: AuthKeys) -> None:
        self.app = app
        self.settings = settings
        self.keys = keys
        self.allowed_origins = frozenset({settings.app_origin, *settings.csrf_trusted_origins})

    def _failure(self, request: Request) -> str | None:
        headers = request.headers
        fetch_site = headers.get("sec-fetch-site")
        if fetch_site is not None and fetch_site != "same-origin":
            return "Cross-site request blocked."
        origin = headers.get("origin")
        if origin is not None and origin not in self.allowed_origins:
            return "Request origin not allowed."
        has_body = headers.get("transfer-encoding") is not None or (
            headers.get("content-length") not in (None, "0")
        )
        content_type = headers.get("content-type", "")
        if has_body and content_type.split(";", 1)[0].strip().lower() != "application/json":
            return "Unsupported content type."
        names = cookie_names(self.settings)
        cookie_token = request.cookies.get(names.csrf)
        header_token = headers.get(CSRF_HEADER)
        if not cookie_token or not header_token:
            return "Missing CSRF token."
        if not hmac.compare_digest(cookie_token, header_token):
            return "CSRF token mismatch."
        if not token_is_valid(self.keys, request.cookies.get(names.session), header_token):
            return "CSRF token invalid for this session."
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] not in SAFE_METHODS
            and scope["path"].startswith("/api/")
            # Service-to-service routes authenticate with a shared-secret header, never with
            # cookies, so a cross-site request cannot ride on a user's session there.
            and not scope["path"].startswith(INTERNAL_PREFIX)
        ):
            request = Request(scope)
            failure = self._failure(request)
            if failure is not None:
                response = problem_response(
                    request,
                    status=403,
                    code="csrf_failed",
                    title="Request blocked for your security. Refresh the page and try again.",
                    detail=failure,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
