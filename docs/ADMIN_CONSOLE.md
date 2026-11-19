# Super Admin Console — Foundation

| | |
|---|---|
| Status | **Foundation, Listening (§8), Reading, Writing, Speaking and Assessment Rubrics (§9) implemented 2026-11-19, awaiting review.** The question bank and remaining modules are marked "Soon" |
| Builds on | Phase 3b authentication & RBAC (opaque sessions, CSRF, seeded roles/permissions), Phase 4 design system, Phase 5a content domain |
| Related | `SECURITY_GUIDELINES.md` §2-4, `API_SPECIFICATION.md` §10, `SYSTEM_ARCHITECTURE.md` ADR-019 |

## 1. What already existed (reused, not rebuilt)

- Roles `super_admin`, `admin`, `content_manager`, `reviewer`, `student` and 21 permissions, seeded by migration `0006` (`admin.access` is held by every staff role, by no student).
- Opaque server-side sessions; the principal (status, roles, permissions) is re-read from the database on **every** request, so revocations, suspensions and role changes apply immediately.
- `require_permission`, `require_staff` (`admin.access` + the staff-2FA gate) and `GET /api/v1/admin/session`.
- CSRF middleware on every unsafe `/api/` request; the sign-in page, account menu ("Admin area" link for staff) and `<StaffOnly>` page guard.
- Placeholder admin routes `/admin/{users,content,imports,reviews,billing,ai-usage,audit-log,settings}` (still present and gated; not linked from the new sidebar).

No second authentication mechanism, role system or table was added. **No database migration** was needed.

## 2. Access workflow

1. The administrator opens the normal **Sign in** page and signs in with the provisioned email and password (`POST /auth/login`, unchanged).
2. The frontend routes by the permissions in the login response: `admin.access` → `/admin`, otherwise `/dashboard`. An explicit, safe `?next=` wins, except that non-staff accounts are never sent into `/admin`. This is a convenience only.
3. `/admin` (layout) asks the backend `GET /api/v1/admin/session`. 401 → redirect to sign-in; 403 → an access-denied page **without** any admin navigation; 200 → the console. Each page re-checks (`<StaffOnly>`), because layouts are not re-rendered on client navigation.
4. Every admin API call is authorised again by the backend (`require_staff_permission`). Nothing the browser sends (role fields, headers, edited JavaScript state) is trusted.
5. Expired (idle 7 d / absolute 30 d by default), revoked, signed-out or suspended sessions get 401 immediately. Sign out (`POST /auth/logout`, CSRF-protected) revokes the session server-side.

## 3. Provisioning staff accounts

There is **no HTTP endpoint and no registration page** that grants a staff role; an account can never promote itself. Roles are assigned by an operator with database access through `scripts/admin_cli.py` (logic in `app/modules/identity/provisioning.py`).

```bash
# Initial Super Admin (creates an active account; prompts for the password without echo)
uv run --env-file .env python scripts/admin_cli.py create-staff owner@example.com --full-name "Owner Name"

# Scripted deployment: the password comes from an environment variable injected from the secret store
INITIAL_ADMIN_PASSWORD=... uv run python scripts/admin_cli.py create-staff owner@example.com \
    --full-name "Owner Name" --role super_admin --password-env INITIAL_ADMIN_PASSWORD

uv run --env-file .env python scripts/admin_cli.py grant-role person@example.com --role content_manager
uv run --env-file .env python scripts/admin_cli.py revoke-role person@example.com --role content_manager
uv run --env-file .env python scripts/admin_cli.py list-staff
```

Rules (all enforced and tested):

- **Passwords are never command-line arguments** (shell history, process lists). They come from a no-echo prompt or from the environment variable named by `--password-env`; they pass the normal password policy, are hashed with Argon2id, and are never printed or logged. Abbreviated flags are disabled, so `--password X` is rejected.
- **Idempotent:** re-running a command changes nothing and writes no audit entry. `create-staff` on an existing account only grants the role and **never changes its password**.
- **Only `active` accounts can be promoted** (email verified, not suspended/deleted). Someone who registered an address without controlling its mailbox cannot be elevated.
- **Every role change revokes the account's existing sessions**, so new privileges always start from a fresh sign-in.
- **The last active super admin cannot be removed** unless `--allow-no-super-admin` is passed.
- **Audited:** `identity.user.provisioned`, `identity.role.granted`, `identity.role.revoked` with `actor_user_id = NULL` and `changes.via = "admin_cli"`.

Configuration: the CLI validates the full application settings, so it needs the deployment's `DATABASE_URL`, `REDIS_URL` and (outside local/ci) `AUTH_SECRET_KEY`. No new environment variable exists; nothing is read from source-controlled config.

## 4. Authorization rules

| Endpoint | Requires (in addition to a live staff session + staff 2FA where required) |
|---|---|
| `GET /api/v1/admin/session` | `admin.access` |
| `GET /api/v1/admin/overview/users` | `users.read` (super_admin, admin) |
| `GET /api/v1/admin/overview/content` | any of `content.edit`, `content.review`, `content.publish` |
| `GET /api/v1/admin/audit-logs?limit=1..50` | `audit.read` (super_admin, admin) |

- `require_staff_permission(*codes)` (identity public API) = `require_staff` + at least one of `codes`. 401 without a live session; 403 `permission_denied` (not staff / missing permission) or `mfa_required`.
- All admin responses are `Cache-Control: no-store`. The audit read is redacted (no IP prefix, no change payload).
- A unit test asserts that every `/api/v1/admin/*` route depends on `require_staff` and that no other router publishes admin routes; another asserts no OpenAPI path manages roles.
- Every mutating admin route added later must audit its change and is CSRF-protected automatically.

## 5. Code structure

| Layer | Where |
|---|---|
| Admin API (composition only, no tables) | `backend/app/modules/admin/` — reads other modules **only via their `api.py`** (import-linter contracts; domain modules never import it) |
| Read models | `identity.api.user_overview` / `display_names`, `content.api.content_overview`, `audit.api.recent` |
| Provisioning | `identity/provisioning.py` + `scripts/admin_cli.py` |
| Console layout | `frontend/src/app/(admin)/admin/layout.tsx` (server gate) → `components/admin/admin-shell.tsx` |
| Navigation | `components/admin/admin-nav.ts` — one source for sidebar, drawer, breadcrumbs, dashboard quick access |
| Dashboard | `app/(admin)/admin/page.tsx` + `components/admin/dashboard/widgets.tsx`; data via `lib/admin/server.ts` |

**Adding a module:** add its route under `src/app/(admin)/admin/<module>/` (wrapped in `<StaffOnly>`), set `href` and `status: "available"` on its nav item, add its backend endpoints behind `require_staff_permission("<permission>")`. Content management must use the existing content domain (question-type registry, validator, review/publish workflow, immutable published versions) through `content.api`, never a parallel model.

## 6. Dashboard

Welcome panel (name, email, role, permission count) · IELTS content quick access (Listening links to its module; the other 4 are "Soon", no links) · Content overview (books, tests, versions by status, published modules by skill) · Accounts (students, all accounts by status, staff by role) · Recent activity (latest audit entries, UTC) · System overview (live `/readyz`). Every number is a live database read; each widget shows an explicit empty state, "your role does not include access", or "could not be loaded" — never sample data.

Sidebar groups: Overview (Dashboard) · IELTS Content (Listening, Reading, Writing, Speaking, Question Bank) · Users (Student, Admin Management) · Business (Subscriptions, Payments) · Insights (Analytics & Reports) · System (Media Library, Audit Logs, Settings). Dashboard and Listening Management are links; the rest are non-interactive "Soon" entries.

## 7. Limitations and open items (foundation)

- **Production blocker (unchanged, deliberate):** staff 2FA (TOTP) is not implemented, and `STAFF_MFA_REQUIRED` cannot be disabled in production. Until it exists, every staff session in production (and staging by default) is refused with `403 mfa_required`; the console shows a "Two-factor authentication required" page. Super admins can be provisioned there, but cannot use the console.
- Staff sessions use the same lifetimes as student sessions (7 d idle / 30 d absolute). A shorter staff timeout is a policy decision not yet made.
- The audit-log endpoint returns only the newest entries (no filters/paging yet); the full Audit Logs page is planned.
- No admin management UI yet: roles change only through the CLI.
- Placeholder routes from Phase 4 (`/admin/users`, `/admin/content`, …) remain reachable by URL (gated, "Not available yet") but are not in the new sidebar; remove or repurpose them when their modules ship.
- Playwright e2e for the console is not set up (project-wide Phase 4 deferral); the flow was verified with real servers against a throwaway database (see the change report).

## 8. Listening Management (2026-11-19)

Staff create, edit, validate, preview, review, publish and archive full IELTS Listening tests at `/admin/listening` (each action by permission; Super Admin has all of them). **No parallel content system:** everything is stored in the existing content domain (Phase 5a) and goes through its question-type registry, import schema, validator, four-eyes review, publishing and immutability rules. The candidate-side Listening exam is **not** part of this phase.

### 8.1 Data model (existing tables)

| Concept | Table | Notes |
|---|---|---|
| Collection | `books` → `book_editions`, under a `content_licenses` row | Picked or created in step 1. Until D-04 is decided, the console can only create **original (in-house)** licences |
| Listening test | `tests` (+ `admin_notes`, new) | `code` = test identifier, unique per edition |
| Version | `test_versions` (+ `description`, `difficulty`, `tags`, new) | draft → in_review → published → archived. Difficulty reuses `easy/medium/hard`, shown as Beginner/Intermediate/Advanced |
| Module | `test_modules` (`listening/common`) | `duration_seconds` = estimated duration |
| Sections 1–4 | `sections` (+ `context`, new) | title, instructions, context, `audio_asset_id` |
| Questions | `question_groups` → `questions` → `question_options`, `answer_keys`, `answer_variants`, `explanations` | unchanged |
| Audio / images | `media_assets` (+ `original_filename`, `uploaded_by`, new) | the bytes live only in object storage |

Migration **0008** adds only the nullable columns marked "new" and extends the immutability trigger so `description`, `difficulty` and `tags` are frozen once a version leaves draft. No new tables.

### 8.2 Admin workflow

1. **Basic information** (`/admin/listening/new`): collection (book + edition; "New collection" creates the book, the edition and, with `content.licenses.manage`, an original licence), title, identifier, difficulty, estimated duration, tags, description, internal notes. Creates the test with draft v1 and four empty sections.
2. **Sections 1–4** (editor `/admin/listening/{versionId}`): title, context, instructions, section audio (upload, preview, replace).
3. **Question builder** per section: add, duplicate, reorder and delete question groups and questions, with the fields each type needs (§8.4). Saving sends the whole draft; the server rebuilds the listening module with the import pipeline (`importer.build_sections`), so the same schema, key notation and validator apply as for JSON imports. `questions.lineage_id` round-trips, so question history survives edits. Saves use optimistic concurrency: `revision` is the `updated_at` the editor loaded, a stale save gets `409 content_draft_conflict`, and the editor never replaces unsaved edits with a newer server copy.
4. **Validate & review:** run validation (publish strictness) → **Submit for review** (`content.edit`; refused with the issue list if anything blocks) → **Approve / Request changes** by a *different* staff member (`content.review`; four-eyes: the author can never review, `403 content_self_review_forbidden`) → **Publish** (`content.publish`; only after an approval given since submission) → **Archive** (published → archived; the test leaves the library but stays readable for history).
5. **Revisions:** published and archived versions are immutable (service layer and database triggers). "Create new revision" deep-copies the live version into draft v(n+1); publishing it archives the previous version in the same transaction. **Duplicate** creates a separate test (new identifier, new question lineages). **Delete draft** discards a draft, and the test too if it had no other version.

The list page shows live counts (total, published, drafts, in review, approved, archived), search (title or identifier), status and difficulty filters, pagination, and per-row actions limited by role and state.

### 8.3 Audio and image storage

- Object storage is S3-compatible: **MinIO** in docker-compose (`minio` service, console http://127.0.0.1:9001). Docker Hub and Quay no longer publish MinIO community images, so compose uses Chainguard's build of the same server, pinned by digest (AGPLv3; run only as a separate local service).
- Flow: the browser hashes the file (SHA-256) → `POST /admin/content/media` (the server checks kind, MIME allow-list, size and checksum format, creates a `media_assets` row in `uploading` and returns a 5-minute presigned PUT) → the browser PUTs the file straight to storage, with real progress → `POST /admin/content/media/{id}/complete` (the server reads the object back: it exists, its size matches and is within the limit, its file signature matches the type, its SHA-256 matches) → `ready`. Otherwise the asset is `failed`, the object is deleted and the API answers `422 media_rejected`. Nothing is reported as uploaded unless the server verified it.
- Allowed: audio MP3, WAV, M4A (≤ `MEDIA_MAX_AUDIO_BYTES`, default 200 MB); images PNG, JPEG, WebP for map, plan and diagram questions (≤ `MEDIA_MAX_IMAGE_BYTES`, default 10 MB). Keys are server-generated (`uploads/{kind}/{uuid}.{ext}`). The bucket is private; staff playback uses 5-minute presigned GETs.
- Assets are immutable: replacing audio uploads a new asset, and the draft points to it once saved. The old asset remains because older versions may still reference it.
- **Not implemented (Phase 5b worker):** malware scanning (ClamAV), quarantine promotion, transcoding and loudness normalisation, duration extraction. That is why `MEDIA_UPLOADS_ENABLED` defaults to on only in local/ci and **cannot be enabled in staging or production** (startup refuses). Without storage configuration uploads return `503 media_storage_unavailable`; with uploads disabled, `503 media_uploads_disabled`.
- Configuration: `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL` (the browser-facing origin used to sign URLs), `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` (created on first upload), `MEDIA_UPLOADS_ENABLED`, `MEDIA_MAX_AUDIO_BYTES`, `MEDIA_MAX_IMAGE_BYTES`. docker-compose needs `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` in `.env`. MinIO accepts browser CORS only from `PUBLIC_APP_URL`.

### 8.4 Question builder and the registry

The builder offers exactly the registry types whose catalog includes Listening (`GET /admin/content/question-types`), under their canonical codes:

| Code | Family | Editor fields |
|---|---|---|
| `mcq_single` | option | options per question, one correct letter |
| `mcq_multi` | multi_option | shared options, number range (one mark per number), N correct letters |
| `matching_features` | option | shared options, "an option may answer several questions" |
| `map_labelling` | option | shared letters, optional map image |
| `form_completion`, `note_completion`, `table_completion`, `sentence_completion`, `short_answer` | text | word limit, "and/or a number", correct answer and accepted alternatives, answer type (words, number, time, date) |
| `flowchart_completion`, `summary_completion`, `plan_labelling`, `diagram_labelling` | text, word bank allowed | as above, or "choose from a list" (`answer_format: option`) with a word bank; optional image for plan and diagram |

Every question has its number(s), a prompt (stored as allow-listed ProseMirror JSON, never HTML), options where applicable, the correct answer, accepted alternatives (existing key notation: `(the) library`, `colour/color`, `a / b`), an explanation and its position. Marks follow the model (one per question number). Errors from the validator **and** from the request schema (for example a question with no answer yet) are shown on the exact section, group and question.

**Gaps (reported, not extended):** completion *templates* (`config.template`: a table or notes layout with numbered blanks) are supported by the handlers but cannot be edited in the builder yet, so each gap is authored as its own question prompt. Explanation audio timestamps are kept but not editable. Section-level duration is not edited (the module duration is).

### 8.5 Validation (existing validator, publish strictness)

Valid licence; exactly sections 1–4; every section has ready audio; question types allowed in Listening; handler checks (options, keys, match modes, word limits, parseable keys, templates); question numbers unique and contiguous 1..N; exactly 40 questions; referenced assets exist and are ready. On save the editor also rejects reading passages in Listening sections, assets of the wrong kind and assets from another licence. Warnings (not blocking): missing explanations, no band-conversion table. Incomplete drafts can be saved; only malformed content is refused at save.

### 8.6 Preview

`/admin/listening/{versionId}/preview` renders the candidate view produced by each type's `student_view` (instructions, options, order, an audio player per part), with an **admin-only** "Show answers" toggle for accepted answers and explanations. It is not an attempt: nothing is answered, scored or stored.

### 8.7 Future candidate API compatibility

Published versions (and archived ones, for history) are read through the existing `content.api.get_student_view`. It returns test metadata, modules, the four sections, `has_audio`, question types, prompts, options, order and the config candidates need (word limits, answer format). It **never** returns answer keys, variants, explanations, admin notes, review data or unpublished versions (tested). Scoring uses the registry handlers with the stored keys. Still needed for the candidate module (Phase 7): an exam-engine endpoint issuing short-lived audio URLs for an attempt's sections (TTL ≈ section duration), entitlements and attempts.

### 8.8 API

All under `/api/v1/admin/content`, behind the staff gate plus a permission, `Cache-Control: no-store`, and CSRF-protected for unsafe methods.

| Method & path | Permission |
|---|---|
| `GET /listening/overview`, `GET /listening/tests?search&status&difficulty&offset&limit` | any of content.edit / review / publish |
| `GET /listening/versions/{id}`, `…/validation`, `…/preview`; `GET /question-types`, `/books`, `/licences`; `GET /media/{id}/url` | any of content.edit / review / publish |
| `POST /listening/tests`; `PUT`, `DELETE /listening/versions/{id}`; `POST …/{id}/duplicate`; `POST /listening/tests/{test_id}/revisions`; `POST …/{id}/submit`; `POST /books`, `POST /books/{id}/editions` | content.edit |
| `POST …/{id}/review` | content.review (never the author) |
| `POST …/{id}/publish`, `POST …/{id}/archive` | content.publish |
| `POST /licences` (original only) | content.licenses.manage |
| `POST /media`, `POST /media/{id}/complete` | media.upload |

Audit entries: `content.test.create`, `content.test.duplicate`, `content.test_version.save_draft`, `…submit`, `…review`, `…publish`, `…unpublish`, `…create_draft`, `…delete_draft`, `content.media.upload_started`, `…uploaded`, `…rejected`, `content.licence.create`, `content.book.create`, `content.edition.create`.

### 8.9 Remaining limitations

- Production is still blocked by staff 2FA (§7) and by the missing malware scan (§8.3).
- One editor at a time with conflict detection: no real-time collaboration or autosave, and uploaded files attach only when the draft is saved.
- No completion-template editor, no CSV import into the editor (Phase 6), no Media Library page.
- Uploaded assets that are never saved into a draft are not cleaned up yet.
- The browser end-to-end check is a local script, not a Playwright suite in CI (project-wide deferral).

## 9. Reading, Writing, Speaking and Rubrics (2026-11-19)

- **Reading** (`/admin/reading`) reuses the Listening editor with 3 passage sections: passage title, labelled paragraphs, `**bold**`/`_italic_`, word count; evidence paragraph per question; TRUE/FALSE/NOT GIVEN, YES/NO/NOT GIVEN and matching types; no audio.
- **Writing** (`/admin/writing`): Academic or General Training at creation; Task 1 (report on an uploaded visual, or letter) and Task 2 (essay): prompt, minimum words, staff-only assessment focus, up to 3 model answers (optional band). Academic Task 1 without a visual is a warning.
- **Speaking** (`/admin/speaking`): Parts 1-3 with topic and examiner questions (follow-up flag); the Part 2 cue card (task, points, closing line) is required; model answers per part.
- Both use the shared catalogue, validation, preview, four-eyes review, publish, archive and revisions. Model answers are immutable once published and shown to candidates only after they submit.
- **Assessment Rubrics** (`/admin/rubrics?module=writing|speaking`): fixed criteria codes (Writing TA/CC/LR/GRA, Speaking FC/LR/GRA/PR); names, descriptions and at least 3 band descriptors are written by staff (no IELTS descriptor text is shipped). Draft -> review by a different staff member -> publish (archives the previous version). AI evaluation is `unavailable` until a rubric is published.

## 10. AI Examiner Configuration (2026-11-19)

`/admin/speaking/examiner` (nav: AI Examiner). Configurations are built on a **published**
Speaking test and reference its existing Part 1/2/3 questions and cue card by index (no second
question store): question selection and order, Part 2 rounding-off questions, timing (Part 1/3
answer time, Part 2 preparation and long turn, whole-test limit), follow-up settings (live
examiner only), difficulty, evaluation criteria, and structured examiner instructions (role,
introduction with `{examiner}`, tone, delivery, follow-ups, irrelevant answers, silence, part
transitions, completion, confidentiality). The side panel previews the exact step sequence and
the 10 conversation rules. Draft -> publish (`content.publish`; blocked while issues remain);
published configurations are read-only (database trigger) until unpublished. Examiner profiles
(three seeded placeholder personas: name, title, personality, style, accent note, difficulty,
avatar colour, active flag) are edited on the same page; their voice settings stay empty until a
voice provider exists. API: `/api/v1/admin/speaking/{examiners,tests,configs,...}`.
