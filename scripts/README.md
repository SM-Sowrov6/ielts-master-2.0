# scripts/

Developer and operator tooling.

- `admin_cli.py` — staff provisioning (create the initial Super Admin, grant/revoke staff roles, list staff). Works in every environment; the only way roles change. See `docs/ADMIN_CONSOLE.md` §3.
- `content_cli.py` — content import/review/publish (refuses production).
- `export_openapi.py`, `check_contrast.py`, `update_password_blocklist.py` — build/CI helpers.

Dev seed scripts must refuse to run when `APP_ENV=production` (docs/DEVELOPMENT_GUIDELINES.md §8).
