"""Fixed-window rate limits in Redis (SECURITY_GUIDELINES.md §7).

Keys hold only hashed subjects (no raw emails or IP addresses) and expire with their window.
Authentication endpoints FAIL CLOSED: if Redis cannot be reached, the request is refused (503)
rather than processed without brute-force protection.
"""

from dataclasses import dataclass

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.modules.identity.errors import RateLimitedError, RateLimiterUnavailableError
from app.modules.identity.tokens import subject_digest

log = structlog.get_logger("app.identity.ratelimit")


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window_seconds: int


# Initial values from SECURITY_GUIDELINES.md §7 ("5/min/IP, 10/hour/account").
LOGIN_IP = Rule("login:ip", 5, 60)
LOGIN_ACCOUNT_FAILURES = Rule("login:account-failures", 10, 3600)
REGISTER_IP = Rule("register:ip", 5, 60)
FORGOT_IP = Rule("forgot:ip", 5, 60)
RESEND_IP = Rule("resend:ip", 5, 60)
RESET_IP = Rule("reset:ip", 5, 60)
VERIFY_IP = Rule("verify:ip", 10, 60)
PASSWORD_CHANGE_USER = Rule("password-change:user", 10, 3600)
# Second-factor attempts per user (6-digit codes: keep guessing far below 1e6).
MFA_USER = Rule("mfa:user", 5, 300)
# Emails to one address (registration notices, verification, reset): prevents mail-bombing a
# victim. Exceeding it is silent, so it never reveals whether an account exists.
EMAIL_ACCOUNT = Rule("email:account", 5, 3600)


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(rule: Rule, subject: str) -> str:
        return f"rl:{rule.name}:{subject_digest(subject)}"

    async def hit(self, rule: Rule, subject: str) -> tuple[int, int]:
        """Count one event. Returns (count in window, seconds until the window resets)."""
        key = self._key(rule, subject)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, rule.window_seconds, nx=True)
                pipe.ttl(key)
                count, _, ttl = await pipe.execute()
        except (RedisError, OSError) as exc:
            log.error("ratelimit.unavailable", rule=rule.name, error=type(exc).__name__)
            raise RateLimiterUnavailableError from exc
        return int(count), max(int(ttl), 1)

    async def count(self, rule: Rule, subject: str) -> tuple[int, int]:
        key = self._key(rule, subject)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.get(key)
                pipe.ttl(key)
                value, ttl = await pipe.execute()
        except (RedisError, OSError) as exc:
            log.error("ratelimit.unavailable", rule=rule.name, error=type(exc).__name__)
            raise RateLimiterUnavailableError from exc
        return int(value or 0), max(int(ttl), 1)

    async def enforce(self, rule: Rule, subject: str) -> None:
        """Count one event and refuse it (429) once the window's limit is exceeded."""
        count, retry_after = await self.hit(rule, subject)
        if count > rule.limit:
            raise RateLimitedError(headers={"Retry-After": str(retry_after)})

    async def ensure_below(self, rule: Rule, subject: str) -> None:
        """Refuse (429) if the limit is already reached, without counting this event."""
        count, retry_after = await self.count(rule, subject)
        if count >= rule.limit:
            raise RateLimitedError(headers={"Retry-After": str(retry_after)})

    async def allow(self, rule: Rule, subject: str) -> bool:
        """Count one event; False once over the limit (for silent quotas)."""
        count, _ = await self.hit(rule, subject)
        return count <= rule.limit

    async def reset(self, rule: Rule, subject: str) -> None:
        try:
            await self._redis.delete(self._key(rule, subject))
        except RedisError, OSError:
            log.warning("ratelimit.reset_failed", rule=rule.name)
