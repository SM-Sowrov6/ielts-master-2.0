"""admin module — the Super Admin console's HTTP API under /api/v1/admin (2026-11-19).

A thin composition layer: it owns no tables and holds no business rules. It authorises each
request (`identity.api.require_staff_permission`) and reads other modules only through their
public `api.py` interfaces. Future admin features (content management, users, billing, ...) add
their endpoints in the owning module or here, always behind the same gate.
"""
