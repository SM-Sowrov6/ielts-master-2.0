"""Identifier generation (ADR-012): time-ordered UUIDv7, generated in the application."""

import uuid


def new_id() -> uuid.UUID:
    """Return a new UUIDv7 (RFC 9562), using the Python 3.14 standard library.

    Time-ordered values keep B-tree inserts local; IDs are non-enumerable and can be generated
    before an INSERT (idempotent creates). PostgreSQL 18's `uuidv7()` is intentionally unused.
    """
    return uuid.uuid7()
