"""IELTS MASTER 2.0 AI engine.

A pure library (ADR-003): no database access, no environment reading, no imports from `app`
(backend) or `ielts_voice`. Callers inject configuration, retrievers, and a usage sink.
"""

__version__ = "0.1.0"
