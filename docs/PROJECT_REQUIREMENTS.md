# IELTS MASTER 2.0 — Project Requirements

| Field | Value |
|---|---|
| Status | **Draft v0.2 — revised after Phase 1 audit, awaiting approval** |
| Phase | 1 — Architecture & Documentation |
| Owners | Technical Lead (architecture), Product Owner (scope) |
| Last updated | 2026-11-17 |

> Conventions: **MUST** = required for the phase that delivers it. **SHOULD** = strongly recommended, can slip with justification. **MAY** = optional / future.
> Requirement IDs (`FR-*`, `NFR-*`) are referenced from the other documents and from tests. Do not renumber; deprecate instead.

---

## 1. Product Vision

IELTS MASTER 2.0 is a commercial SaaS platform where a student can **learn, practise, sit realistic mock exams, receive AI evaluation, and track band-score progress** for all four IELTS modules (Listening, Reading, Writing, Speaking) in Academic and General Training variants.

Version 2 is a **ground-up rebuild**. No code, schema, or infrastructure from Version 1 (https://www.ieltsmaster.site/) is reused. User/data migration from V1 is an open decision (see §9, D-09).

### 1.1 Goals

1. One platform covering the full IELTS preparation loop: content → practice → exam → evaluation → analytics → coaching.
2. Database-driven content: adding books, tests, or questions never requires a code change.
3. Trustworthy AI evaluation: rubric-based, evidence-backed, clearly labelled as *estimates*.
4. Natural, low-latency AI speaking practice.
5. Production-grade security, privacy, reliability, and cost control from day one.
6. An architecture a growing team can work on in parallel.

### 1.2 Non-goals (initial releases)

- Official IELTS certification or any claim of equivalence to official scores.
- Native mobile apps (the web app MUST be responsive; native apps MAY come later and will reuse the REST API).
- Microservices / Kubernetes (see `SYSTEM_ARCHITECTURE.md` ADR-001, ADR-009).
- Live human tutoring marketplace.
- Multi-tenant white-labelling for institutions (MAY be added later; schema should not block it).

---

## 2. Personas & Roles

| Role | Description | Key capabilities |
|---|---|---|
| **Visitor** | Unauthenticated | Public pages, pricing, sample content, sign-up |
| **Student** | Registered learner (free or paid plan) | Library, practice, exams, AI evaluation, speaking partner, dashboard, coach |
| **Reviewer** | Content QA | Review/approve/reject content versions, comment |
| **Content Manager** | Content author | Create/edit books, tests, questions, media; run imports; submit for review |
| **Admin** | Operations | User management, subscriptions, payments monitoring, AI usage, analytics, publishing |
| **Super Admin** | Platform owner | Everything incl. role management, system configuration, destructive operations |

Roles map to permissions (RBAC) — see `SECURITY_GUIDELINES.md` §4.

---

## 3. Functional Requirements

### 3.1 Identity & Accounts (FR-ID)

| ID | Requirement | Priority |
|---|---|---|
| FR-ID-01 | Email + password registration with email verification | MUST |
| FR-ID-02 | Login, logout, logout-all-devices | MUST |
| FR-ID-03 | Password reset via single-use, expiring token | MUST |
| FR-ID-04 | Google OAuth sign-in (see D-06) | SHOULD |
| FR-ID-05 | Profile: name, target band, test type (Academic/GT), exam date, country, timezone | MUST |
| FR-ID-06 | Session list with device info and revoke | SHOULD |
| FR-ID-07 | Account deletion and personal-data export (self-service) | MUST |
| FR-ID-08 | Consent capture (terms, privacy, audio recording) with versioning | MUST |
| FR-ID-09 | Admin: search, view, suspend, reactivate users; assign roles | MUST |
| FR-ID-10 | MFA (TOTP) for staff roles | SHOULD (MUST before production for Admin/Super Admin) |

### 3.2 Book Library & Content (FR-LIB, FR-CMS)

| ID | Requirement | Priority |
|---|---|---|
| FR-LIB-01 | Browse books with pagination, cover, edition, variant (Academic/GT), module coverage | MUST |
| FR-LIB-02 | Full-text search over book titles/descriptions; filters: book, edition, category, module, variant | MUST |
| FR-LIB-03 | Book detail → list of tests → per-test module/section entry points | MUST |
| FR-LIB-04 | Start practice for: whole test, a module, a section, a question type | MUST |
| FR-LIB-05 | Book-wise and test-wise progress (completion %, best/last score) | MUST |
| FR-LIB-06 | Review incorrect answers with explanations after an attempt | MUST |
| FR-LIB-07 | Access control by plan entitlement (free vs premium content) | MUST |
| FR-CMS-01 | CRUD for books, editions, tests, modules, sections, passages, paragraphs, question groups, questions, options, answer keys, variants, explanations, writing tasks, speaking topics/cue cards | MUST |
| FR-CMS-02 | Media upload (audio, images) via signed URLs, with validation and processing | MUST |
| FR-CMS-03 | Bulk import: JSON (canonical) and CSV (question-level) with dry-run validation report | MUST |
| FR-CMS-04 | Draft → In review → Published → Archived workflow per test version | MUST |
| FR-CMS-05 | Content preview rendered exactly as students see it (practice & exam modes) | MUST |
| FR-CMS-06 | Immutable published versions; edits create a new draft version | MUST |
| FR-CMS-07 | Licence/rights record per book; publishing blocked without valid licence record | MUST |
| FR-CMS-08 | Document-processing assisted import (PDF/DOCX → structured draft, human-verified) | MAY (Phase 6+) |
| FR-CMS-09 | Audit trail for every content change | MUST |

### 3.3 Question Bank (FR-QB)

| ID | Requirement | Priority |
|---|---|---|
| FR-QB-01 | Support all question types listed in `QUESTION_BANK_DESIGN.md` §3 | MUST |
| FR-QB-02 | Single reusable rendering/validation/scoring pipeline with type-specific handlers | MUST |
| FR-QB-03 | Question groups with shared instructions, shared option lists, shared images/tables | MUST |
| FR-QB-04 | Accepted answer variants, case/whitespace normalisation, word-limit rules ("NO MORE THAN TWO WORDS AND/OR A NUMBER") | MUST |
| FR-QB-05 | Multi-mark questions (e.g., "Choose TWO letters" = 2 marks) | MUST |
| FR-QB-06 | Tagging: question type, skill, difficulty, topic | MUST |
| FR-QB-07 | Question-type-specific practice sets drawn across published tests | MUST |

### 3.4 Examination Engine (FR-EX)

| ID | Requirement | Priority |
|---|---|---|
| FR-EX-01 | Exam types: Full Mock, single-module (L/R/W/S), book-based, custom, randomized, question-type practice | MUST (custom/randomized SHOULD) |
| FR-EX-02 | Practice mode and Exam mode as separate, explicit modes with distinct rules | MUST |
| FR-EX-03 | Server-authoritative timers, per section/module | MUST |
| FR-EX-04 | Autosave each answer to server; idempotent; survives refresh/network loss/crash | MUST |
| FR-EX-05 | Resume an in-progress attempt from any device | MUST |
| FR-EX-06 | Question navigation, previous/next, mark-for-review, review panel | MUST |
| FR-EX-07 | Safe, idempotent submission; auto-submit at deadline | MUST |
| FR-EX-08 | Automatic objective scoring; raw score → estimated band conversion | MUST |
| FR-EX-09 | Writing and Speaking in exams routed to AI evaluation asynchronously | MUST |
| FR-EX-10 | Results report: per module, per section, per question type; answer review | MUST |
| FR-EX-11 | Attempt history with filters | MUST |
| FR-EX-12 | Listening replay rules configurable per mode (exam: single play) | MUST |
| FR-EX-13 | Practice mode: instant feedback, explanations, optional hints, re-attempt | MUST |

### 3.4a Reading & Listening Module Experience (FR-RL) — *added after Phase 1 audit (brief §8)*

| ID | Requirement | Priority |
|---|---|---|
| FR-RL-01 | Reading: passage rendering with paragraph labels and paragraph navigation (jump to paragraph A–H); split view passage/questions on desktop, tabbed on mobile | MUST |
| FR-RL-02 | Reading: text highlighting and private notes on passages during an attempt (persisted on the device per attempt, never shared; server-side sync MAY be added later with its own schema) | SHOULD |
| FR-RL-03 | Listening: audio player with play/pause (practice), progress indicator, section indicator, volume; replay/seek governed by mode rules (FR-EX-12) | MUST |
| FR-RL-04 | Listening: transcript and timestamped explanations available after completion (where licensed) | SHOULD |
| FR-RL-05 | Book-wise, test-wise, section-wise and question-type practice for both modules; Academic & GT where applicable | MUST |
| FR-RL-06 | Answer input types matching each question type (text blanks, option selects, drag-and-drop with keyboard alternative) | MUST |

### 3.5 Writing Evaluation (FR-WR)

| ID | Requirement | Priority |
|---|---|---|
| FR-WR-01 | Academic Task 1, GT Task 1, Task 2 support | MUST |
| FR-WR-02 | Rich-text-free distraction-free editor (plain text in exam mode), live word count | MUST |
| FR-WR-03 | Criterion bands (TA/TR, CC, LR, GRA) + overall estimated band | MUST |
| FR-WR-04 | Evidence-backed feedback: every criticism cites a verbatim span of the response | MUST |
| FR-WR-05 | Sentence-level corrections, grammar analysis, vocabulary upgrades, coherence analysis, task relevance, missing-information detection (Task 1 key features) | MUST |
| FR-WR-06 | Improved model response at a target band | SHOULD |
| FR-WR-07 | Submission history and progress comparison | MUST |
| FR-WR-08 | Prominent "AI estimate, not an official IELTS score" disclosure | MUST |
| FR-WR-09 | Free-practice submissions with custom prompts (moderated) | SHOULD |
| FR-WR-10 | Sample answers for writing tasks (and speaking sample material) shown **only where licensed** | SHOULD |

### 3.6 Speaking Partner (FR-SP)

| ID | Requirement | Priority |
|---|---|---|
| FR-SP-01 | Real-time voice session via WebRTC (LiveKit) | MUST |
| FR-SP-02 | Modes: Part 1, Part 2 (with 1-minute prep + up to 2-minute long turn), Part 3, full mock, topic practice, interviewer-style practice, free conversation | MUST |
| FR-SP-03 | Natural turn-taking: VAD, end-of-turn detection, barge-in/interruption handling, reconnect after network drop | MUST |
| FR-SP-04 | Explicit consent before any session: `voice_processing` consent required to start; separate optional `audio_recording` consent required before any audio is stored. Without recording consent, sessions run without storage and without pronunciation scoring | MUST |
| FR-SP-05 | Post-session evaluation: FC, LR, GRA, Pronunciation bands; filler/repetition analysis; transcript | MUST |
| FR-SP-06 | Pronunciation assessed from audio (not transcript only) | MUST |
| FR-SP-07 | Session history, playback of own recordings (subject to retention) | SHOULD |
| FR-SP-08 | Per-plan limits on minutes/sessions | MUST |

### 3.7 AI Learning Coach (FR-CO)

| ID | Requirement | Priority |
|---|---|---|
| FR-CO-01 | Weakness detection from actual performance data | MUST |
| FR-CO-02 | Personalised study plan toward target band and exam date | MUST |
| FR-CO-03 | Recommendations: tests, question types, daily practice | MUST |
| FR-CO-04 | Weekly progress summary (in-app; email optional) | SHOULD |
| FR-CO-05 | Coach chat grounded in the student's data and authorised learning resources (RAG) | SHOULD |
| FR-CO-06 | Coach never fabricates scores or progress; all numbers come from tool calls | MUST |

### 3.8 Student Dashboard (FR-DB)

FR-DB-01 … MUST display: overall estimated band, per-module performance, recent exams, book/test completion, accuracy by question type, weak question types, trends, streaks, recommendations, recent AI feedback. Data comes from pre-aggregated tables (see `LEARNING_ANALYTICS_DESIGN.md`).

### 3.9 Admin (FR-AD)

User & role management, content CMS, imports, review, publishing, media library, subscriptions, payments monitoring, AI usage & cost monitoring, platform analytics, audit log viewer, system configuration (feature flags, provider routing, quotas). All MUST, delivered across phases per `DEVELOPMENT_ROADMAP.md`.

### 3.10 Billing (FR-BI)

| ID | Requirement | Priority |
|---|---|---|
| FR-BI-01 | Plans with entitlements (content access, AI quotas, speaking minutes) | MUST |
| FR-BI-02 | Subscription lifecycle: trial, active, past_due, cancelled, expired | MUST |
| FR-BI-03 | Payment provider integration with verified, idempotent webhooks (provider: D-01) | MUST |
| FR-BI-04 | Per-user usage metering and enforcement | MUST |
| FR-BI-05 | Invoices/receipts | SHOULD |
| FR-BI-06 | Coupons / promotional pricing | MAY |

### 3.11 Notifications (FR-NO)

Transactional email (verification, reset, evaluation ready, weekly summary) — MUST. In-app notifications — SHOULD. Email provider is an implementation detail behind an interface.

---

## 4. Non-Functional Requirements

### 4.1 Performance (initial targets, revisited after load tests)

| ID | Metric | Target |
|---|---|---|
| NFR-PF-01 | API p95 latency, read endpoints (cached) | < 200 ms |
| NFR-PF-02 | API p95 latency, autosave answer | < 150 ms |
| NFR-PF-03 | Exam start (load full test version) p95 | < 800 ms |
| NFR-PF-04 | Speaking voice-to-voice response latency p50 / p95 (target; to be validated by the Phase 10 prototype, measured in production) | < 1.2 s / < 2.0 s |
| NFR-PF-05 | Writing evaluation completion p95 | < 90 s |
| NFR-PF-06 | Speaking post-session evaluation p95 | < 5 min |
| NFR-PF-07 | Public page LCP (4G, mid-range phone) | < 2.5 s |
| NFR-PF-08 | Concurrent active exam attempts supported by baseline deployment | 1,000 (scale path to 10,000+) |

### 4.2 Reliability

| ID | Requirement |
|---|---|
| NFR-RL-01 | Zero acknowledged-answer loss: an answer the server acknowledged is never lost |
| NFR-RL-02 | Availability target 99.5% monthly initially (99.9% later) |
| NFR-RL-03 | RPO ≤ 15 min (PITR), RTO ≤ 4 h for database |
| NFR-RL-04 | All background jobs idempotent and retry-safe |
| NFR-RL-05 | AI provider outage degrades gracefully (queue + fallback provider), never corrupts attempts |

### 4.3 Security & Privacy

OWASP ASVS Level 2 as the baseline; detailed in `SECURITY_GUIDELINES.md`. Ownership checks on every student resource (NFR-SE-01). No secrets in repo (NFR-SE-02). Audio recordings private, consented, retention-limited (NFR-SE-03). GDPR-style data subject rights (export, deletion) offered globally (NFR-SE-04).

### 4.4 Maintainability

Typed code (mypy strict on backend/ai packages, TypeScript strict), enforced module boundaries, ≥ 80% line coverage on domain/service layers, OpenAPI as the API contract, documentation updated in the same PR as behaviour changes.

### 4.5 Accessibility

WCAG 2.2 AA for student-facing UI, including the exam interface (keyboard navigation, focus management, screen-reader labels, sufficient contrast, adjustable text size).

### 4.6 Observability

Structured JSON logs with request/trace IDs, Prometheus metrics, Grafana dashboards, Sentry error tracking (frontend & backend), LangSmith tracing for AI workflows (PII-redacted), cost dashboards for AI usage.

### 4.7 Cost

AI spend per active user tracked daily; per-plan quotas enforced before provider calls; budget alerts at 50/80/100% of monthly budget.

---

## 5. Content Licensing Constraint (critical)

Commercial IELTS books (e.g., Cambridge IELTS series) are copyrighted. The platform MUST NOT host or distribute copyrighted material without a written licence. The system enforces this technically (FR-CMS-07): every book references a `content_licenses` record (source type: *original*, *licensed*, *public-domain*, *user-generated*), and publishing is blocked without one. Sample answers and speaking samples follow the same rule. See `CONTENT_MANAGEMENT_ARCHITECTURE.md` §2.

---

## 6. Assumptions

| # | Assumption | Impact if wrong |
|---|---|---|
| A-1 | Single primary region at launch; users mostly in one geography | Latency for voice; may need LiveKit region selection |
| A-2 | Small team initially (2–6 engineers) | Modular monolith fits; revisit at 15+ |
| A-3 | English UI first; i18n-ready string handling (D-08) | Retrofitting i18n is expensive — we externalise strings from day one |
| A-4 | Students may include minors (16–17) | Consent and parental-consent rules; see `SECURITY_GUIDELINES.md` §11 |
| A-5 | Managed services acceptable for Postgres, Redis, object storage, LiveKit | Self-hosting raises ops load considerably |

---

## 7. Constraints

- Tech stack as specified in the initialization brief (Next.js / FastAPI / PostgreSQL / Redis / Celery / LangGraph / LiveKit), with deviations documented as ADRs in `SYSTEM_ARCHITECTURE.md`.
- No Kubernetes initially.
- Phase-gated delivery: each phase is reviewed and approved before the next begins.

---

## 8. Success Metrics (post-launch)

- Exam completion rate ≥ 85% of started full mocks (excluding abandoned within 2 min).
- AI writing band within ±0.5 of the human reference score for ≥ 70% of held-out benchmark essays, ±1.0 for ≥ 95%. **Provisional:** re-baselined against measured human inter-rater agreement (`AI_ENGINE_ARCHITECTURE.md` §8.1).
- Speaking voice latency within NFR-PF-04 for ≥ 95% of turns.
- Zero P1 security incidents; zero acknowledged answer loss.

---

## 9. Open Decisions (require Product Owner input)

| ID | Decision | Recommended default | Blocks phase |
|---|---|---|---|
| D-01 | Payment provider(s) — depends on target markets and where the business entity is registered | Abstract `PaymentProvider`; Stripe for international cards if eligible; local gateway (e.g., SSLCommerz / bKash) if the primary market requires it | 12 |
| D-02 | LiveKit Cloud vs self-hosted LiveKit server | LiveKit Cloud initially (ops burden, TURN, global edge) | 10 |
| D-03 | Pronunciation assessment provider | Azure AI Speech Pronunciation Assessment behind `PronunciationAssessor` interface | 10 |
| D-04 | Content sources & licences for the first 10–20 books | In-house original tests + any formally licensed titles | 5/6 |
| D-05 | Hosting provider for app servers | Docker Compose on 2+ VMs (AWS/Hetzner/DigitalOcean) + managed Postgres/Redis | 2 |
| D-06 | Social login providers | **Deferred by Product Owner (2026-11-17).** No social login until decided | later (not 3) |
| D-07 | Default LLM/STT/TTS providers per task | Decided by evaluation benchmark in Phase 8, not by preference | 8 |
| D-08 | UI languages beyond English | English at launch, i18n-ready | 4 |
| D-09 | Migrate V1 users/data? | Migrate accounts (email + name) only, with re-consent; no content migration | 13 |
| D-10 | Free-tier scope | Limited tests + small AI quota | 12 |
| D-11 | Default branch name: repo currently has an empty local `master`; docs assume `main` | Rename to `main` before first commit | 2 |
| D-12 | Data retention periods (speaking audio, transcripts, coach chats, logs, traces) | Proposed defaults in `SECURITY_GUIDELINES.md` §11; legal confirmation required | 13 (design in 10) |
| D-13 | Minimum user age, parental consent requirement and verification method | **Partly decided by Product Owner (2026-11-18): minimum age 16+, no parental-consent flow; self-declared age confirmation checkbox, recorded as an `age_confirmation` consent (`minimum-age:16`).** Configured via `REGISTRATION_MINIMUM_AGE=16`, not hard-coded. The Product Owner is responsible for confirming 16+ without parental consent is lawful in each target market (legal review, Phase 13) | 3b, 13 |
| D-17 | Terms of Service and Privacy Policy (text and versions) needed for registration consent (FR-ID-08) | Provided by the Product Owner / legal review; never written by engineering | 3b (production registration), 13 |
| D-18 | Production email provider (SMTP), data-processing agreement, sending domain (SPF/DKIM/DMARC) | Any SMTP-capable provider; the integration is provider-neutral; Mailpit in development | 3b (production), 14 |
| D-14 | Student access to completed attempts' content after a content licence lapses | Depends on licence terms; options: keep review access, hide content but keep scores, or remove | 6 |
| D-15 | Human rater sourcing and budget for benchmark datasets (≥ 2 raters per sample) | Contract experienced IELTS raters; budget before Phase 9 | 9 |
| D-16 | Use of the public IELTS band descriptors (embedding in prompts; displaying excerpts to students) | Embed for internal assessment; display only paraphrased guidance unless usage permission confirmed | 9 |
