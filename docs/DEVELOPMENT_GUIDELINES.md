# IELTS MASTER 2.0 — Development Guidelines

| Field | Value |
|---|---|
| Status | **Draft v0.2 — revised after Phase 1 audit; awaiting approval** |
| Applies to | Everyone contributing code, content tooling, or docs |
| Last updated | 2026-11-17 |

---

## 1. Toolchain

| Area | Tool | Notes |
|---|---|---|
| Python | 3.14 (ADR-018) managed by **uv** (workspace: backend, ai-engine, voice-engine) | single `uv.lock` |
| Python quality | **ruff** (lint + format), **mypy --strict**, **import-linter** (module boundaries), Bandit | |
| Node | Current Node LTS (exact version pinned in `.nvmrc` / `engines` during Phase 2), **pnpm** via Corepack | `frontend/` |
| TS quality | ESLint 9 flat config (`eslint-config-next` core-web-vitals + typescript), `pnpm typecheck` (`next typegen && tsc --noEmit`). Prettier (`frontend/.prettierrc.json`; generated and vendored files ignored), active since Phase 4 | |
| Git hooks | **pre-commit** (ruff, prettier, gitleaks, end-of-file, large-file check) | |
| Local services | Docker Compose. **Phase 2:** postgres+pgvector, redis, backend, frontend. Added in the phase that first needs them: minio/S3 (Phase 5 media), mailpit (Phase 3 email), worker + flower (first Celery task), livekit-server dev (Phase 10) | incremental |
| Task runner | Cross-platform commands (`uv run …`, `pnpm …`, `docker compose …`) documented in the README. A `Makefile` is optional convenience, because Windows developers may not have `make` | |

## 2. Backend Conventions

- **Layering:** router → service → repository → models (see `SYSTEM_ARCHITECTURE.md` §3.3). Routers have no business logic. Repositories have no business rules. Services own transactions.
- **Async:** async SQLAlchemy (`asyncpg`) in the API. Never block the event loop (CPU-heavy or sync SDK calls go to workers or `run_in_threadpool`).
- **Dependency injection:** FastAPI dependencies for `CurrentUser`, `UnitOfWork`, settings, and permission checks. Services are constructed with explicit dependencies (testable without FastAPI).
- **Types:** Full type hints. `Mapped[...]` ORM models. Pydantic v2 schemas. No `Any` in public signatures without justification.
- **Errors:** Raise domain exceptions (`AttemptDeadlinePassed`). A single exception handler maps them to problem+json with stable `code`. Never return 500 for expected domain conditions.
- **Time:** Use `shared.time.now()` (injectable clock) and never call `datetime.now()` directly in domain code. Tests freeze time.
- **IDs:** `shared.ids.new_id()` (UUIDv7).
- **Config:** `core.config.Settings` only. No `os.environ` reads elsewhere.
- **Celery tasks:** thin, idempotent, typed args (IDs only), explicit `max_retries`, `autoretry_for` limited to transient errors.
- **Logging:** `structlog.get_logger()`. Use key-value events (`log.info("attempt.submitted", attempt_id=…)`) and never log PII or content bodies.

## 3. Frontend Conventions

- **Server vs client components:** Server Components by default. `"use client"` only for interactivity (exam shell, editors, charts, forms). Data for initial render is fetched on the server, and mutations/live data use TanStack Query on the client.
- **State:** server state → TanStack Query. Ephemeral UI/exam-session state → Zustand (one store per feature, no global god-store). Form state → React Hook Form + Zod, rendered with `FormTextField` / shadcn `field` (shadcn v4 has no `form` component).
- **API:** only the generated client in `src/lib/api`. No hand-written fetch to backend paths in components.
- **Structure:** `src/features/<domain>/{components,hooks,stores,api}`. `components/ui` holds design-system primitives only (shadcn/ui) with no domain logic. `components/patterns` holds reusable composed UI, and `components/layout` holds the shells. Details: `FRONTEND_DESIGN_SYSTEM.md`.
- **Server/client boundary:** never pass functions (icons, callbacks, components) from a Server Component to a Client Component. Pass serialisable keys.
- **Frontend checks:** `pnpm format:check`, `pnpm lint`, `pnpm typecheck`, `pnpm test` (Vitest + axe-core), `pnpm build`, `python -I scripts/check_contrast.py`.
- **Styling:** Tailwind with design tokens (CSS variables) and dark mode support. No ad-hoc colour hex values in components.
- **Accessibility:** semantic HTML, labelled controls, visible focus, keyboard paths for all interactions (incl. drag-and-drop alternatives), `axe` checks in component and e2e tests.
- **Motion:** subtle, respects `prefers-reduced-motion`, none in the exam interface beyond essential feedback.
- **Rich text:** TipTap in the CMS and the writing editor (practice). The exam writing editor is a plain textarea (closer to the real test, no formatting). Content is rendered from ProseMirror JSON via an allow-listed renderer.
- **Charts:** Recharts, wrapped in shared chart components for consistent theming. Deferred to Phase 11 (first real data); not installed yet.

## 4. API Contract Workflow

1. Design the endpoint in a PR touching `API_SPECIFICATION.md` (or a short design note) **before** implementation for any new resource.
2. Implement backend with Pydantic schemas. OpenAPI is generated.
3. CI regenerates the TS client and fails if the committed client differs (`pnpm api:generate && git diff --exit-code`).
4. Breaking changes require the `api-breaking` label and a frontend PR in the same release.

## 5. Database Workflow

- One linear Alembic history. Rebase migrations onto `main` before merge and renumber `down_revision` if needed (CI checks a single head).
- Migration PRs must state: purpose, lock impact, backfill plan, rollback plan.
- Expand/contract for breaking changes (`DATABASE_SCHEMA.md` §10). Destructive steps need the `db-destructive` label and explicit approval.
- Do not edit merged migrations. Add new ones.
- Commands (repo root): `uv run --env-file .env alembic -c backend/alembic.ini upgrade head` · `... downgrade -1` · `... revision -m "<slug>" --rev-id <next 4-digit number>` · `... check` (drift). Every new model module must be imported in `backend/migrations/env.py`.
- Models inherit `app.core.orm.Base` and use `UUIDPrimaryKeyMixin` / `TimestampMixin`. Never create a second `MetaData` in application code (tests use a separate probe metadata on purpose).

## 6. Git & Collaboration

### 6.1 Branching (trunk-based with short-lived branches)

- `main` is always deployable and protected (required reviews + green CI, linear history via squash merge).
- Feature branches: `<type>/<scope>-<short-desc>`, e.g. `feat/exams-autosave`, `fix/auth-refresh-reuse`, `docs/api-writing`, `chore/ci-trivy`. Optional ticket key: `feat/IM-142-exams-autosave`.
- Branches live ≤ 3–5 days. Large features ship behind **feature flags** in smaller PRs.
- Releases are tagged `vX.Y.Z` from `main`. Hotfix: `hotfix/<desc>` → `main` → tag.
- *Note:* the repository currently has a local `master` branch with no commits, while the plan assumes `main` as the default. Rename to `main` before the first commit (D-11, trivial).

### 6.2 Commits — Conventional Commits

`<type>(<scope>): <imperative summary>`. Types: `feat, fix, docs, refactor, perf, test, build, ci, chore, revert`. Scopes = module names (`exams`, `content`, `frontend`, `ai-engine`, `voice`, `infra`). Example: `feat(exams): add idempotent answer autosave endpoint`.

### 6.3 Pull Requests

- Small (< ~400 changed lines excluding generated code/tests where possible), single concern.
- Template sections: Summary · Scope (module) · Screenshots (UI) · API/DB changes · Security checklist (if applicable) · Tests run · Docs updated · Risks/rollback.
- Required: green CI (lint, types, tests, scans, migration check, client drift), ≥ 1 approval from CODEOWNER, **2 approvals** for `identity`, `billing`, `exams` scoring/persistence, security config, migrations.
- Reviewers check correctness, boundaries, security, tests, and docs, in that order.
- Do not merge your own PR without review. No force-push to `main`.

### 6.4 Module ownership

`CODEOWNERS` maps directories to owners (see `SYSTEM_ARCHITECTURE.md` §10). Changes in another team's module require their review. Cross-module changes go through the target module's `api.py`.

## 7. Definition of Done

A task is **done** only when:
- [ ] Code implements only the approved scope.
- [ ] Unit + integration tests added/updated and passing locally and in CI.
- [ ] Types, lint, and boundary checks pass.
- [ ] Security checklist completed (if applicable).
- [ ] Docs updated (API spec, schema doc, ADR if a decision changed).
- [ ] Observability: logs/metrics for new critical paths.
- [ ] Feature-flagged if incomplete for users.
- [ ] Status reported honestly as **completed / pending / unverified**.

## 8. Environments

| Env | Purpose | Data |
|---|---|---|
| `local` | Docker Compose | dev seed data only (`scripts/seed_dev`, clearly fake) |
| `ci` | ephemeral | fixtures |
| `staging` | prod-like, auto-deployed from `main` | synthetic + licensed test content; **no real student data** |
| `production` | live | real |

Mock/demo data is never loaded into production. Seed scripts refuse to run when `ENV=production`.

## 9. Environment Setup (verified in Phase 2)

```bash
git clone … && cd ielts-master
cp .env.example .env            # fill local-only values
uv sync                         # Python workspace
pnpm --dir frontend install     # frontend
pre-commit install
docker compose up -d            # postgres, redis, backend, frontend (Phase 2 set)
uv run --package ielts-backend pytest
```
These commands were run and verified in Phase 2. The root `README.md` is the maintained reference (prerequisites, Docker and native workflows, CI-equivalent checks).

## 10. Documentation Rules

- Docs live in `docs/` and change in the same PR as the behaviour.
- New significant decision → append an ADR in `SYSTEM_ARCHITECTURE.md` §8 (or split into `docs/adr/` when > 20 ADRs).
- Diagrams in Mermaid, kept next to the text they explain.
