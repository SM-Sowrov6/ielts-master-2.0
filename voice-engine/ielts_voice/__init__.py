"""IELTS MASTER 2.0 voice engine (LiveKit Agents worker) — package boundary only until Phase 10.

Boundary rules (enforced by import-linter): never imports the backend package `app`; talks to the
backend only via the authenticated internal HTTP API; may use `ielts_ai` provider interfaces.
"""

__version__ = "0.1.0"
