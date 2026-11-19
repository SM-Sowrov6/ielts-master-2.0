"""Export the backend OpenAPI schema for frontend type generation.

    uv run python scripts/export_openapi.py            # writes frontend/src/lib/api/openapi.json
    cd frontend && pnpm api:generate                   # -> src/lib/api/schema.d.ts

No database or Redis connection is made: the app is built with placeholder settings and only
`app.openapi()` is called. Output is deterministic (sorted keys) so CI can detect drift.
"""

import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "api" / "openapi.json"


def main() -> int:
    settings = Settings(
        app_env="ci",
        database_url="postgresql://openapi:export@127.0.0.1:9/unused",
        redis_url="redis://127.0.0.1:9/0",
        log_level="WARNING",
    )
    schema = create_app(settings).openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
