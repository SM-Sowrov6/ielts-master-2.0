"""Password hashing (Argon2id) and policy (SECURITY_GUIDELINES.md §2, NIST SP 800-63B).

- Passwords are NFKC-normalised before hashing and checking, so visually identical input from
  different keyboards/IMEs matches. Length is counted in code points: 10..128.
- No composition rules. Rejected: entries of the common-password blocklist (see
  scripts/update_password_blocklist.py for source and licence) and passwords that are, or
  contain, the account's email address/local part or the service name.
- Hashing runs in a thread pool behind a semaphore, so Argon2's memory cost cannot exhaust the
  host under concurrent requests. Unknown accounts are "verified" against a decoy hash so that
  response timing does not reveal whether an email is registered.
"""

import asyncio
import gzip
import unicodedata
from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 10
MAX_LENGTH = 128
_SERVICE_NAMES = ("ieltsmaster", "ielts master", "ielts-master")


def normalize_password(password: str) -> str:
    return unicodedata.normalize("NFKC", password)


@lru_cache(maxsize=1)
def common_passwords() -> frozenset[str]:
    data = resources.files("app.modules.identity").joinpath("data/common-passwords.txt.gz")
    text = gzip.decompress(data.read_bytes()).decode("utf-8")
    return frozenset(line for line in text.splitlines() if line and not line.startswith("#"))


def policy_problem(password: str, *, email: str) -> str | None:
    """Return a user-facing reason the password is not acceptable, or None."""
    value = normalize_password(password)
    if len(value) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(value) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    lowered = value.casefold()
    if lowered in common_passwords():
        return "This password is too common. Choose something harder to guess."
    local_part = email.casefold().split("@", 1)[0]
    if lowered == email.casefold() or (len(local_part) >= 4 and local_part in lowered):
        return "Don't use your email address in your password."
    if any(name in lowered for name in _SERVICE_NAMES):
        return "Don't use the site name in your password."
    return None


class PasswordService:
    def __init__(self, *, memory_kib: int, iterations: int, concurrency: int) -> None:
        self._hasher = PasswordHasher(
            time_cost=iterations,
            memory_cost=memory_kib,
            parallelism=1,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._semaphore = asyncio.Semaphore(concurrency)
        self._decoy: str | None = None

    async def hash(self, password: str) -> str:
        async with self._semaphore:
            return await asyncio.to_thread(self._hasher.hash, normalize_password(password))

    async def verify(self, password_hash: str | None, password: str) -> bool:
        """Constant-work check: an unknown account (None) still costs one Argon2 verification."""
        if password_hash is None and self._decoy is None:
            self._decoy = await self.hash("decoy password for timing equalisation")
        target = password_hash if password_hash is not None else self._decoy
        if target is None:  # pragma: no cover — the decoy is set above
            return False
        async with self._semaphore:
            try:
                await asyncio.to_thread(self._hasher.verify, target, normalize_password(password))
            except VerifyMismatchError, VerificationError, InvalidHashError:
                return False
        return password_hash is not None

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)
