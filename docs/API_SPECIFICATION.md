# IELTS MASTER 2.0 — API Specification

| Field | Value |
|---|---|
| Status | **Draft v0.2 — revised after Phase 1 audit; contract outline, awaiting approval** |
| Style | REST/JSON, versioned path `/api/v1`; WebSocket/SSE only where justified |
| Source of truth | FastAPI-generated **OpenAPI 3.1** (`/api/v1/openapi.json`, staff-only in production); this document defines conventions and the endpoint inventory |
| Last updated | 2026-11-17 |

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Base path | `/api/v1` (public + student), `/api/v1/admin/*` (staff), `/internal/v1/*` (service-to-service, not routed publicly by Nginx) |
| Format | JSON, UTF-8, `snake_case` fields; timestamps ISO-8601 UTC (`2026-11-17T10:00:00Z`); IDs UUID strings |
| Auth | httpOnly cookies `__Host-access` (Path=/) / `__Secure-refresh` (Path=/api/v1/auth/refresh) (web), or `Authorization: Bearer` (future mobile). CSRF header `X-CSRF-Token` on unsafe methods for cookie auth |
| Errors | RFC 9457 `application/problem+json`: `{type, title, status, detail?, instance, code, errors?[], request_id}`; `type` = `urn:ielts-master:problem:<code>`; `code` is a stable machine string (e.g., `attempt_deadline_passed`). Implemented in `backend/app/core/errors.py` |
| Validation errors | 422 with `errors: [{loc, msg, code}]` |
| Pagination | Cursor-based for growing collections: `?limit=20&cursor=…` → `{items, next_cursor}`. Offset (`page`, `page_size`) only for admin tables where total counts are needed |
| Filtering/sorting | Explicit allow-listed query params (`?module=reading&sort=-created_at`). No arbitrary field filters |
| Idempotency | `Idempotency-Key` header required on: attempt submit, payment checkout, evaluation requests, imports commit. Stored 24 h (Redis + DB uniqueness where durable) |
| Concurrency | Optimistic locking for CMS edits via `If-Match: <version>` → 412 on conflict |
| Rate limits | Headers `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`; 429 with `Retry-After` |
| Request ID | `X-Request-ID` accepted/echoed; included in problem responses |
| Versioning | Additive changes within v1. Breaking change → `/api/v2` route group, with v1 deprecation window ≥ 6 months and the `Deprecation` header |
| Client generation | Frontend TypeScript **types** generated from OpenAPI (`scripts/export_openapi.py` → `openapi-typescript`) and used via `openapi-fetch`. CI job `api-contract` fails on drift. **Zod schema generation is deferred** (Phase 4 decision, `FRONTEND_DESIGN_SYSTEM.md` §5) until the first form binds to a real API |

### 1.1 Authorization notation

`public` · `auth` (any logged-in user) · `owner` (resource belongs to current user) · `perm:<code>` (RBAC permission) · `ent:<key>` (plan entitlement). Every endpoint lists its requirements, and tests assert them (see `TESTING_STRATEGY.md` §3.3).

---

## 2. Identity — `/auth`, `/me`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | rate-limited; sends verification email; generic response (no account enumeration) |
| POST | `/auth/verify-email` | public | `{token}` |
| POST | `/auth/login` | public | sets cookies; lockout/backoff after failures |
| POST | `/auth/refresh` | refresh cookie | rotation; reuse → revoke session family |
| POST | `/auth/logout` | auth | revokes current session |
| POST | `/auth/logout-all` | auth | revokes all sessions |
| POST | `/auth/password/forgot` | public | generic response |
| POST | `/auth/password/reset` | public | `{token, new_password}` revokes all sessions |
| GET | `/auth/oauth/google/start` · `/callback` | public | PKCE + state |
| GET | `/auth/csrf` | public | issues CSRF token |
| GET/PATCH | `/me` · `/me/profile` | auth | |
| GET/DELETE | `/me/sessions` · `/me/sessions/{id}` | auth/owner | |
| POST | `/me/consents` | auth | `{consent_type, document_version, granted}` |
| POST | `/me/data-export` | auth | async; emailed signed link |
| DELETE | `/me` | auth | re-auth required; 14-day grace then purge |
| POST | `/me/mfa/totp/setup` · `/verify` · DELETE | auth | required for staff |

**Implemented (2026-11-18):** `GET /auth/csrf`; `GET /auth/registration-policy` (open/closed, minimum age, legal versions, development-placeholder flag); `POST /auth/register` (202, identical for new and existing emails); `POST /auth/verify-email` (204, or 400 `token_invalid`); `POST /auth/verify-email/resend` (202); `POST /auth/login` (200 `MeResponse` + cookies, 401 `invalid_credentials`, 403 `email_not_verified`, 429); `POST /auth/logout` (204); `POST /auth/logout-all` (204); `POST /auth/password/forgot` (202); `POST /auth/password/reset` (204, revokes all sessions, does **not** verify the email); `GET /me`; `POST /me/password` (204, rotates this session, revokes others); `GET /admin/session` (staff gate: `admin.access`, plus staff 2FA where required, otherwise 403 `mfa_required`). Also 403 `csrf_failed`, 403 `registration_closed`, 422 `password_policy` / `consent_required`, 503 `rate_limiter_unavailable`. Auth responses are `Cache-Control: no-store`. **Not implemented:** `/auth/refresh` (opaque sessions, ADR-006 revised), OAuth (D-06), session list, consents API, data export, account deletion, MFA endpoints.

## 3. Library (student read) — `/library`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/library/books` | public | filters: `q, category, variant, module, series`; cursor |
| GET | `/library/books/{slug}` | public | editions + tests summary + `access: free\|premium\|locked` |
| GET | `/library/tests/{test_id}` | public | modules/sections summary (no content bodies) |
| GET | `/library/question-types` | public | types with counts available |

Content bodies are delivered **only through attempts** (`/attempts/{id}/content`), so entitlement, mode, and key-stripping are always applied.

**Route ownership.** Each path prefix belongs to exactly one module: `/auth`, `/me`, `/me/sessions`, `/me/consents` → identity · `/library` → content · `/exam-templates`, `/attempts` → exams · `/writing` → writing · `/speaking` → speaking · `/me/dashboard`, `/me/stats`, `/me/progress`, `/me/activity`, `/me/recommendations` → analytics/coach · `/coach` → coach · `/billing` → billing · `/notifications` → notifications. Per-user progress for a book lives under analytics (`GET /me/progress/books/{book_id}`), not under `/library`, because content must not read analytics data.

## 4. Exams — `/exam-templates`, `/attempts`

**Implemented (2026-11-19, Listening):** `GET /listening/tests` (published, non-draft tests + the caller's progress; `search`, `difficulty`), `GET /listening/tests/{test_id}` (sections summary, mode rules, own attempts); `POST /attempts` (`Idempotency-Key` header; `{test_id, mode}`), `GET /attempts` (own history), `GET /attempts/{id}`, `POST …/start`, `POST …/resume`, `GET …/content` (key-stripped), `GET …/answers`, `PUT …/answers` (batch ≤ 50, `X-Writer-Token`), `POST …/sections/{n}/audio-url`, `GET …/sections/{n}/groups/{g}/image-url`, `POST …/submit` (`Idempotency-Key`, `X-Writer-Token`; 200 with the completed attempt), `GET …/result`, `GET …/review` (completed only). Other users' attempts answer 404. Errors: `attempt_open_exists` (with `attempt_id`), `attempt_submitted`, `attempt_deadline_passed`, `superseded_session`, `writer_token_invalid`, `question_not_in_attempt`, `response_invalid`, `attempt_already_submitted`, `entitlement_required`, `test_unavailable`, `audio_unavailable`. `/listening/*` is owned by exams (it joins published content with the caller's attempts). Deviations from the table below: `EXAMINATION_ENGINE_DESIGN.md` §0.

**Implemented (2026-11-19, Reading/Writing/Speaking):**
- AI Speaking Room (`/speaking`): `GET /examiners`, `GET /room-tests` (published examiner configurations), `POST /rooms` `{examiner_id, config_id, voice_processing_consent: true, audio_recording_consent: true}`, `GET /rooms`, `GET /rooms/{id}` (status, examiner, timing, current step, transcript, voice status, evaluation), `POST /rooms/{id}/enter` (returns the voice connection or null in guided mode), `POST /rooms/{id}/advance` `{step}` (needs a verified recording of that answer; retries are idempotent), `POST /rooms/{id}/end`. Answers upload through `/sessions/{id}/recordings`. Admin: `/admin/speaking/examiners`, `/admin/speaking/tests`, `/admin/speaking/configs` (+ `/preview`, `/publish`, `/unpublish`). Internal: `POST /internal/speaking/rooms/{id}/events` (`X-Internal-Token`, CSRF-exempt service route; disabled without `SPEAKING_EVENTS_TOKEN`).
- Reading: `GET /{module}/tests` and `/{module}/tests/{test_id}` with `module` = `listening` | `reading`; `POST /attempts` takes `module`; `GET /attempts?module=`; review items carry `evidence_paragraph`.
- Writing (`/writing`, owner-only): `GET /tests`, `GET /tests/{id}` (tasks + own submissions), `GET /tests/{id}/tasks/{n}/image` (presigned), `POST /submissions` `{test_id, task_no}` (the open draft, or a new one with a frozen task snapshot), `GET /submissions`, `GET /submissions/{id}` (latest evaluation; model answers only after submit), `PUT /submissions/{id}` `{body, client_revision, time_spent_seconds}` (older revision -> `409 stale_revision`), `POST /submissions/{id}/submit` (`Idempotency-Key`; immutable afterwards, `409 submission_locked`), `POST /submissions/{id}/evaluations` (`Idempotency-Key`; retry after `failed`/`unavailable`, else `409 evaluation_not_retryable`).
- Speaking (`/speaking`, owner-only): `GET /tests`, `GET /tests/{id}` (parts, consent version), `POST /sessions` `{test_id, mode, voice_processing_consent: true, audio_recording_consent: true}` (stores both consents), `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/recordings` (presigned PUT ticket; webm/ogg/mp4/wav, <= 25 MB), `POST …/recordings/{rid}/complete` (size + SHA-256 + signature check; `422 recording_rejected`), `GET …/recordings/{rid}/url`, `POST /sessions/{id}/submit` (`Idempotency-Key`; every question needs a verified recording, else `409 recordings_incomplete`), `POST /sessions/{id}/evaluations`.
- Evaluation object: `status` queued | running | succeeded | failed | unavailable | rejected_input; bands only when succeeded; `not_assessed` (e.g. `PR` without an audio assessor); `message`, `retryable`, provider/model/prompt version.
- Admin: `/admin/content/{module}/overview|tests` accept all four modules (`variant` on create for Writing); `PUT /admin/content/versions/{id}/productive` (Writing tasks / Speaking parts with model answers); `/admin/content/rubrics` (list by `module`, create, get, save, delete draft, submit, review, publish).

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/exam-templates` | auth | available templates for user |
| POST | `/attempts` | auth + ent | `{template_code, test_id?, module?, section_ids?, question_type?, mode}` (mode ∈ template `allowed_modes`) → 201 `created` |
| GET | `/attempts` | auth | own history; filters `status, module, mode`; cursor |
| GET | `/attempts/{id}` | owner | state, timers (`server_now`, deadlines), navigation state, current `writer_epoch` (never the token) |
| POST | `/attempts/{id}/start` | owner | idempotent; returns `{writer_epoch, writer_token, deadlines, server_now}` (ADR-013) |
| POST | `/attempts/{id}/resume` | owner | explicit device takeover: issues a new lease (`writer_epoch + 1`); older leases get `409 superseded_session` |
| GET | `/attempts/{id}/content` | owner | student view of the pinned version (key-stripped); ETag-cached |
| GET | `/attempts/{id}/answers` | owner | all saved answers + revisions (resume) |
| PUT | `/attempts/{id}/answers/{question_id}` | owner + lease | header `X-Writer-Token`; body `{response, writer_epoch, client_revision, flagged}` → `{stored_epoch, stored_revision, saved_at, server_now}`. Stale revision → 200 no-op with stored values. Stale epoch → 409 `superseded_session`. Past grace → 409 `attempt_deadline_passed` |
| PUT | `/attempts/{id}/answers` | owner + lease | batch ≤ 50, one transaction |
| POST | `/attempts/{id}/sections/{section_id}/advance` | owner | finish current timed scope |
| POST | `/attempts/{id}/sections/{section_id}/audio-url` | owner | signed URL; exam mode counts plays |
| POST | `/attempts/{id}/answers/{question_id}/check` | owner, practice | instant feedback |
| GET | `/attempts/{id}/questions/{question_id}/hint` | owner, practice, ent | |
| POST | `/attempts/{id}/submit` | owner + lease | `Idempotency-Key`; optional body `{writer_epoch, final_answers[] ≤ 200}` applied with revision rules inside the submit transaction → 202 |
| GET | `/attempts/{id}/status` | owner | polling |
| GET | `/attempts/{id}/events` | owner | SSE: `status_changed`, `evaluation_ready`. Fan-out across API replicas via Redis pub/sub. Nginx `proxy_buffering off` on this location, and clients fall back to polling |
| GET | `/attempts/{id}/result` | owner | after `completed` (partial when `awaiting_ai`) |
| GET | `/attempts/{id}/review` | owner | answers + keys + explanations, after completion only |

## 5. Writing — `/writing`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/writing/tasks` | auth | standalone practice tasks; filters |
| POST | `/writing/submissions` | auth | draft (`writing_task_id`, or a custom prompt that is moderated first; `attempt_id` when inside an exam). The prompt is snapshotted into `prompt_snapshot` |
| PUT | `/writing/submissions/{id}` | owner (+ lease when `attempt_id` set) | autosave body with `writer_epoch` + `client_revision`. Inside an attempt, deadline/lease checks go through `exams.api.assert_writable` |
| POST | `/writing/submissions/{id}/evaluate` | owner + ent | `Idempotency-Key`; reserves quota → 202 |
| GET | `/writing/submissions` | auth | history, cursor |
| GET | `/writing/submissions/{id}` | owner | includes latest evaluation status |
| GET | `/writing/evaluations/{id}` | owner | full report |
| GET | `/writing/progress` | auth | criterion trends |

## 6. Speaking — `/speaking`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/speaking/sessions` | auth + ent + `voice_processing` consent | `{mode, topic_id?, attempt_id?, record: bool}` (`record=true` requires `audio_recording` consent) → `{session_id, livekit_url, token, max_duration_seconds, recording_enabled}` |
| GET | `/speaking/sessions` | auth | history |
| GET | `/speaking/sessions/{id}` | owner | status, transcript (when available) |
| POST | `/speaking/sessions/{id}/end` | owner | student-initiated end |
| GET | `/speaking/sessions/{id}/recording-url` | owner | signed URL ≤ 5 min |
| DELETE | `/speaking/sessions/{id}/recording` | owner | immediate purge |
| GET | `/speaking/evaluations/{id}` | owner | |
| GET | `/speaking/topics` | auth | topic bank for practice |

Internal (voice engine, service token scoped to one session):

| Method | Path | Notes |
|---|---|---|
| GET | `/internal/v1/speaking/sessions/{id}/script` | mode config, questions, cue card, limits |
| GET/PUT | `/internal/v1/speaking/sessions/{id}/state` | resume state for agent restarts |
| POST | `/internal/v1/speaking/sessions/{id}/turns` | batched turns (idempotent by `seq`) |
| POST | `/internal/v1/speaking/sessions/{id}/end` | end reason, durations |
| POST | `/internal/v1/usage` | voice usage events |

Webhooks: `POST /api/v1/webhooks/livekit` (signature verified).

## 7. Coach & Analytics — `/me/dashboard`, `/coach`

| Method | Path | Auth |
|---|---|---|
| GET | `/me/dashboard` | auth |
| GET | `/me/stats/modules` · `/me/stats/question-types` · `/me/activity` | auth |
| GET | `/me/progress/books/{book_id}` | auth | per-test completion and best/last scores (analytics read model) |
| GET | `/me/recommendations` · POST `/me/recommendations/{id}/dismiss` | auth/owner |
| GET/POST | `/coach/study-plan` (generate → 202) · PATCH `/coach/study-plan/items/{id}` | auth + ent |
| POST | `/coach/conversations` · `/coach/conversations/{id}/messages` (SSE stream response) | auth + ent |
| GET | `/coach/conversations/{id}` | owner |

## 8. Billing — `/billing`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/billing/plans` | public | |
| GET | `/billing/subscription` | auth | current plan, entitlements, usage this period |
| POST | `/billing/checkout` | auth | `Idempotency-Key` → provider checkout URL/session |
| POST | `/billing/subscription/cancel` · `/resume` | auth | |
| GET | `/billing/payments` | auth | receipts |
| POST | `/webhooks/payments/{provider}` | provider signature | idempotent on `provider_event_id` |

## 9. Notifications — `/notifications`

`GET /notifications` (cursor), `POST /notifications/{id}/read`, `GET/PUT /notifications/preferences`.

## 10. Admin — `/admin`

All admin routes require MFA-verified staff sessions and specific permissions. Every mutation is audited.

**Implemented (2026-11-19, `app/modules/admin`, see `ADMIN_CONSOLE.md`):** `GET /admin/overview/users` (`users.read`: totals by status, students, staff by role), `GET /admin/overview/content` (any of `content.edit`/`content.review`/`content.publish`: books, tests, versions by status, published modules by skill), `GET /admin/audit-logs?limit=1..50` (`audit.read`: newest entries, redacted, no filters yet), plus `GET /admin/session` (identity). All read-only, `Cache-Control: no-store`, 401/403 problem responses. **By design there is no role-granting endpoint yet**; roles change only via `scripts/admin_cli.py` (ADR-019).

**Implemented (2026-11-19, Listening management):** `/admin/content/*`: Listening overview and list (search, status, difficulty, offset paging), create, get/save/delete draft (optimistic `revision`), validation, admin preview (with answers), duplicate, new revision, submit, review, publish, archive; books, editions and licences (original only); question types; media upload intent, completion (server verification) and short-lived playback URL. Table and permissions: `ADMIN_CONSOLE.md` §8.8. Content validation failures return `422 content_validation_failed` with an `issues` array (`severity`, `code`, `location`, `message`). Media errors: `422 media_rejected`, `409 media_invalid_state`, `503 media_storage_unavailable` / `media_uploads_disabled`. The generic `/admin/books…`, `/admin/test-versions…` and `/admin/imports` routes in the table below are still planned.

| Area | Endpoints (abridged) | Permission |
|---|---|---|
| Users | `GET /admin/users` (offset, search), `GET/PATCH /admin/users/{id}`, `POST …/suspend` `…/reactivate`, `PUT …/roles` | `users.read` / `users.manage` / `roles.assign` |
| Roles | `GET /admin/roles`, `PUT /admin/roles/{id}/permissions` | `roles.manage` (super_admin) |
| Licences | CRUD `/admin/licenses` | `content.licenses.manage` |
| Books/editions/tests | CRUD `/admin/books`, `/admin/editions`, `/admin/tests` | `content.edit` |
| Versions | `POST /admin/tests/{id}/versions` (new draft from current), `GET/PATCH /admin/test-versions/{id}` (tree editing via nested resources), `POST …/submit`, `…/review`, `…/publish`, `…/unpublish`, `GET …/preview?mode=` , `GET …/validate` | `content.edit` / `content.review` / `content.publish` |
| Items | CRUD under `/admin/test-versions/{id}/modules/…/sections/…/groups/…/questions/…` | `content.edit` |
| Media | `POST /admin/media` (presign), `POST /admin/media/{id}/complete`, `GET /admin/media` | `media.upload` |
| Imports | `POST /admin/imports` (upload → dry run), `GET /admin/imports/{id}` (report), `POST /admin/imports/{id}/commit` | `content.import` |
| Exam templates & band tables | CRUD `/admin/exam-templates`, `/admin/band-tables` | `exams.configure` |
| Billing | `/admin/plans`, `/admin/subscriptions`, `/admin/payments` (read), manual adjustments | `billing.read` / `billing.manage` |
| AI ops | `/admin/ai/usage`, `/admin/ai/routes` (provider routing), `/admin/ai/prompt-versions`, `/admin/ai/eval-runs`, `POST /admin/ai/re-evaluate` | `ai.read` / `ai.manage` |
| Audit | `GET /admin/audit-logs` (filters: actor, entity, action, date) | `audit.read` |
| System | `/admin/feature-flags`, `/admin/settings` | `system.configure` (super_admin) |
| Analytics | `/admin/analytics/*` | `analytics.read` |

## 11. Health & Ops

`GET /healthz` (liveness), `GET /readyz` (DB/Redis checks), `GET /metrics` (Prometheus; bound to the internal network only).

## 12. Example: autosave

```http
PUT /api/v1/attempts/0193…/answers/0193…
Content-Type: application/json
X-CSRF-Token: …

X-Writer-Token: …

{"response": {"text": "carbon dioxide"}, "writer_epoch": 1, "client_revision": 7, "flagged": false}
```
```http
200 OK
{"stored_epoch": 1, "stored_revision": 7, "saved_at": "2026-11-17T10:21:04.512Z", "server_now": "2026-11-17T10:21:04.530Z", "deadline_at": "2026-11-17T11:00:00Z"}
```
```http
409 Conflict
Content-Type: application/problem+json
{"type": "urn:ielts-master:problem:attempt_deadline_passed", "title": "Attempt deadline passed", "status": 409, "code": "attempt_deadline_passed", "instance": "/api/v1/attempts/0193…/answers/0193…"}
```
