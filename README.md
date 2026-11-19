# IELTS MASTER 2.0

An AI-powered IELTS preparation platform covering the book library, practice, full mock exams, AI Writing evaluation, a real-time AI Speaking Partner, analytics, and coaching.

**Status:** All four modules implemented 2026-11-19, awaiting review: Reading (admin + candidate, reusing the Listening engine), Writing and Speaking (admin authoring with model answers, versioned four-eyes rubrics, candidate drafts/recordings, AI evaluation as a background job). **AI evaluation needs a provider:** none is bundled (decision D-07 open), so evaluations end `unavailable` with no score until one is registered in `app/core/ai.py`; tests use test doubles. Earlier: Candidate Listening (practice and exam-mode attempts, autosave, server scoring, review) implemented 2026-11-19, awaiting review. Listening management (admin CMS module with verified audio upload to MinIO) implemented 2026-11-19, awaiting review. Super Admin console foundation (provisioning CLI, admin API authorization, console shell and dashboard) implemented 2026-11-19, awaiting review — see [docs/ADMIN_CONSOLE.md](docs/ADMIN_CONSOLE.md). Phase 5a (Content Domain) done, awaiting review. Service skeletons, the database foundation, the frontend design system with application shells, and the backend content domain (schema, 18 question types, versioning/publishing, JSON import via CLI) exist. Authentication & RBAC (Phase 3b) exist; no student-facing learning features or admin content API yet. Dev-only component gallery: http://127.0.0.1:3000/design-system (`pnpm dev`).

Architecture and plans: [docs/README.md](docs/README.md).

> AI-generated band scores on this platform are estimates and are not official IELTS results.

## Repository layout

| Path | What it is |
|---|---|
| `frontend/` | Next.js (App Router, TypeScript, Tailwind) web app |
| `backend/` | FastAPI modular monolith (package `app`); Celery workers later run from the same image |
| `ai-engine/` | Pure Python library `ielts_ai`: AI provider interfaces, prompt registry, future LangGraph workflows |
| `voice-engine/` | Package boundary for the future LiveKit Agents runtime (`ielts_voice`) |
| `infrastructure/docker/` | Dockerfiles |
| `docs/` | Architecture documentation |
| `scripts/`, `tests/` | Dev tooling; cross-service e2e (Playwright) and load (k6) suites, filled in later phases |

## Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.14 | `.python-version`; uv picks it up |
| uv | 0.13.9 | Windows: `winget install astral-sh.uv` (restart the shell afterwards so `uv` is on PATH) |
| Node.js | ≥ 26 (CI and Docker use 26.13.1 LTS) | |
| Corepack | 0.36.0 | Not bundled with Node ≥ 25: `npm install -g corepack@0.36.0` then `corepack enable pnpm` |
| pnpm | 12.21.0 | Pinned via `frontend/package.json` `packageManager`; Corepack fetches it |
| Docker | Docker Desktop with Compose v2+ | |

## Local setup

```bash
cp .env.example .env              # then set POSTGRES_PASSWORD (URL-safe characters only),
                                  # AUTH_SECRET_KEY, MINIO_ROOT_PASSWORD (= S3_SECRET_ACCESS_KEY)

# Python workspace (backend, ai-engine, voice-engine + dev tools)
uv sync --all-packages

# Frontend
cd frontend && pnpm install && cd ..
```

### Option A: everything in Docker

```bash
docker compose up --build -d --wait
```

| Service | URL (localhost only) | Health |
|---|---|---|
| frontend | http://127.0.0.1:3000 (status page: `/status`) | `/healthz` |
| migrate | one-off: `alembic upgrade head`, then exits (backend waits for it) | exit code 0 |
| backend | http://127.0.0.1:8000 (OpenAPI docs: `/api/v1/docs`, non-production only) | `/healthz` (liveness), `/readyz` (Postgres + Redis) |
| postgres | 127.0.0.1:5432 (PostgreSQL 18 + pgvector 0.8.1, volume `postgres-data`) | `pg_isready` |
| redis | 127.0.0.1:6379 (ephemeral) | `redis-cli ping` |
| minio | 127.0.0.1:9000 (S3 API), console 127.0.0.1:9001 (volume `minio-data`) | started |

Stop with `docker compose down` (data is kept). `docker compose down -v` **deletes** the database volume.

### Option B: databases in Docker, apps native (hot reload)

```bash
docker compose up -d --wait postgres redis
uv run --env-file .env alembic -c backend/alembic.ini upgrade head
uv run --env-file .env uvicorn app.main:create_app --factory --reload --port 8000
cd frontend && pnpm dev            # reads API_INTERNAL_URL from the environment / frontend/.env.local
```

## Checks (same as CI)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/app ai-engine/ielts_ai voice-engine/ielts_voice
uv run mypy backend/migrations
uv run mypy backend/tests && uv run mypy ai-engine/tests && uv run mypy voice-engine/tests
uv run lint-imports                # module-boundary contracts
uv run pytest                      # integration tests skip unless the variables below are set

# Integration tests against the Docker PostgreSQL/Redis (they create and drop their own `ielts_test` DB):
TEST_DATABASE_ADMIN_URL=postgresql://ielts:<POSTGRES_PASSWORD>@127.0.0.1:5432/postgres \
TEST_REDIS_URL=redis://127.0.0.1:6379/0 \
TEST_S3_ENDPOINT_URL=http://127.0.0.1:9000 TEST_S3_ACCESS_KEY_ID=<MINIO_ROOT_USER> TEST_S3_SECRET_ACCESS_KEY=<MINIO_ROOT_PASSWORD> \
REQUIRE_INTEGRATION_TESTS=1 uv run pytest

# Migrations (see docs/DEVELOPMENT_GUIDELINES.md §5)
uv run --env-file .env alembic -c backend/alembic.ini current
uv run --env-file .env alembic -c backend/alembic.ini revision -m "<slug>" --rev-id 0002

cd frontend
pnpm format:check && pnpm lint && pnpm typecheck && pnpm test && pnpm build
python -I ../scripts/check_contrast.py   # WCAG AA contrast of design tokens

# API types after backend API changes (CI fails on drift)
uv run python scripts/export_openapi.py && cd frontend && pnpm api:generate
```

## Candidate Listening (local)

1. Publish a Listening test: as an admin in `/admin/listening` (create → audio → questions → submit), approve it as a *different* staff account (four-eyes), then publish.
2. Sign in as a student and open **Listening** in the sidebar (`/listening`), pick the test, choose practice or exam mode and start.
3. Exam-mode deadlines are enforced lazily and by the `worker` service (`python -m app.workers.outbox`), which also auto-submits expired attempts every 30 s.

## Content operations

Listening tests are managed in the admin console at <http://localhost:3000/admin/listening> (staff account required; audio uploads need the `minio` service). Other modules still use the CLI below. Details: [docs/ADMIN_CONSOLE.md §8](docs/ADMIN_CONSOLE.md).

```bash
uv run --env-file .env python scripts/content_cli.py --help
uv run --env-file .env python scripts/content_cli.py licence-create --source-type original --licensor "..."
uv run --env-file .env python scripts/content_cli.py import FILE.json --licence <ID> --actor <UUID>   # dry-run
uv run --env-file .env python scripts/content_cli.py import-commit <JOB_ID> --actor <UUID>          # creates a draft
# then: submit -> review (a different actor) -> publish
```

Import format: [docs/schemas/test-version-import.schema.json](docs/schemas/test-version-import.schema.json). The CLI refuses `APP_ENV=production`, and **no real third-party content may be imported until D-04 (content rights) is resolved.** Test fixtures are synthetic.

Optional git hooks: `uvx pre-commit install` (see `.pre-commit-config.yaml`).

## Accounts and email (local development)

1. In `.env`, set `AUTH_SECRET_KEY` (at least 32 random characters), e.g. the output of
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Docker Compose refuses to start without it.
2. `docker compose up --build -d` applies migrations 0002-0007 and starts the API, the outbox
   `worker` (sends email) and `mailpit`.
3. Register at <http://localhost:3000/register>, then open the verification email in Mailpit at
   <http://127.0.0.1:8025>. Password-reset emails arrive there too.
4. Minimum age is 16+ (D-13, decided 2026-11-18; `REGISTRATION_MINIMUM_AGE=16`). The Terms of
   Service and Privacy Policy (D-17) are still pending, so local/ci show a marked placeholder and
   every other environment keeps registration closed until their versions are configured.
5. Staff accounts (Super Admin console at <http://localhost:3000/admin>): there is no staff
   registration. Provision an account with the CLI, then sign in on the normal Sign in page:

   ```bash
   uv run --env-file .env python scripts/admin_cli.py create-staff you@example.com --full-name "Your Name"
   # prompts for the password (never pass it as an argument); --role defaults to super_admin
   uv run --env-file .env python scripts/admin_cli.py list-staff
   ```

   Details, roles and rules: [docs/ADMIN_CONSOLE.md](docs/ADMIN_CONSOLE.md). Staff access is refused
   in production (and staging by default) until staff two-factor authentication is implemented.

## Rules that apply from day one

- Never commit `.env` or any secret. `.env.example` holds placeholders only.
- Branch from `main`; Conventional Commits; PRs need green CI ([docs/DEVELOPMENT_GUIDELINES.md](docs/DEVELOPMENT_GUIDELINES.md)).
- Keep docs in sync with code in the same PR.
