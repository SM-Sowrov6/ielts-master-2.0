# Phase 1 Architecture Review — Audit Record

| Field | Value |
|---|---|
| Date | 2026-11-17 |
| Scope | All 15 documents in `docs/`, `docs/README.md`, root `README.md` (v0.1) |
| Result | 40 findings (2 Critical, 11 High, 22 Medium, 5 Low). All corrected in v0.2 or converted to open decisions |
| Evidence key | **V** = verified by reading the documents · **A** = depends on an external fact (vendor behaviour, IELTS policy) not verifiable offline |

## Findings and resolutions

| ID | Sev | Location (v0.1) | Finding | Resolution (v0.2) |
|---|---|---|---|---|
| C-01 | Critical | EXAM §5, §9 | A new epoch on every resume makes post-reload journal replay fail with `409`, so unacknowledged answers are lost (V) | Writer lease persisted with the journal. Explicit takeover. ADR-013. EXAM §5.1 |
| C-02 | Critical | EXAM §5 vs SYS §4 | Autosave unlocked vs submit: an acknowledged save can commit after submit and be missed by scoring. SYS and EXAM contradict each other (V) | Autosave `FOR SHARE`, submit `FOR UPDATE`. EXAM §5.2, SYS §4, DB §5 |
| H-01 | High | EXAM §7, SYS §3.1 | exams ↔ writing dependency cycle (V) | Event-driven orchestration. ADR-014. SYS §3.1, EXAM §7 |
| H-02 | High | SPK §2 | No way for the agent to obtain its session-scoped token (V; LiveKit metadata visibility A) | Token in dispatch metadata + voice-engine service identity fallback. SPK §2 |
| H-03 | High | DB §3, §11; SEC §11 | Append-only `audit_logs` vs pseudonymisation/FK `SET NULL`. Insert-only `payment_events` vs `processed_at` (V) | ADR-016 (no FK on log actors). Column-level UPDATE grant on `payment_events`. DB §3, §7, §11 |
| H-04 | High | AI §4.1 | Verbatim-quote check presented as the main accuracy control. Quotes prove location, not correctness (V) | New `verify_claims` node. Benchmark agreement is the accuracy measure. AI §4 |
| H-05 | High | AI §8 | Benchmark methodology incomplete (V) | Rater protocol, adjudication, human ceiling, splits, feedback audit. AI §8.1, D-15 |
| H-06 | High | SPK §6 | Only recording consent, yet live audio goes to third-party processors (V) | Separate `voice_processing` and `audio_recording` consents. SPK §6, DB §3, §6, API §6, REQ FR-SP-04 |
| H-07 | High | SPK §2–3 | Egress start before the student track exists, no consent re-check (V; webhook semantics A) | Egress on `track_published` after consent re-check. SPK §2–3 |
| H-08 | High | QB §5, DB §4 | Numeric/time/date answers, optional-word notation, "AND/OR A NUMBER" semantics, `text` match mode missing (V) | QB §5, §5.1, §5.2. DB `match_mode` |
| H-09 | High | DB §5 vs EXAM §2 | Single template `mode` vs student choice. Rules not per mode (V) | `allowed_modes` + `default_mode`, rules keyed by mode. EXAM §2, DB §5, API §4 |
| H-10 | High | ROADMAP §2 | Phase 7 needs entitlements from Phase 8; dependency not modelled (V) | Edge P8 → P7 + note. ROADMAP §2, Phase 7 |
| H-11 | High | EXAM §5, DB §6, API §5 | Exam writing autosave lacks revision/ownership. Prompts not snapshotted. No custom prompt storage (V) | `writer_epoch`/`client_revision`/`prompt_snapshot`. EXAM §5.3, DB §6, API §5 |
| M-01 | Med | DB §5 | Polymorphic `section_ref` without FK (V) | `test_module_id` + `section_id` FKs |
| M-02 | Med | EXAM §4 | Grace could be used as extra answering time (V) | UI lock at deadline, grace for in-flight only, late saves flagged |
| M-03 | Med | EXAM §6 vs API §4 | Submit final batch not in API (V) | `final_answers` body. API §4, EXAM §6 |
| M-04 | Med | EXAM §9 | Open-attempt index ignores `created` and NULL test version (V) | Two partial unique indexes. EXAM §9 |
| M-05 | Med | DB §4 | Immutability trigger blocks publish/archive transitions; FK cycle undocumented (V) | Trigger scope + FK cycle documented. DB §4 |
| M-06 | Med | EXAM §2 | Full-mock variant resolution undefined (V) | EXAM §2 |
| M-07 | Med | EXAM §7 | Bands produced for partial modules (V) | Bands only for complete modules |
| M-08 | Med | EXAM §7 | Writing-module rounding stated as official (A) | Labelled a configurable, versioned assumption |
| M-09 | Med | CMS §5 | Semicolon inside a sequence-diagram message (V lint) | Split into two messages |
| M-10 | Med | REQ | Brief items missing: Reading highlight/notes, paragraph navigation, audio progress, interviewer mode, licensed samples, realtime voice provider (V) | FR-RL-01…06, FR-WR-10, FR-SP-02, `sample_answers`, `RealtimeVoiceProvider` + ADR-015 |
| M-11 | Med | API §3 | Library progress route needs analytics data (boundary violation) (V) | `/me/progress/books/{book_id}` owned by analytics. Route-ownership table |
| M-12 | Med | SYS §5–6, CMS §5 | Direct enqueues bypass outbox; "Redis loss is safe" overstated (V) | ADR-017. SYS §5.2, §6. CMS §5 |
| M-13 | Med | DEPLOY §1 | "Redis lock-guarded" beat is not a Celery feature (V) | Single pinned replica; RedBeat as an option needing approval |
| M-14 | Med | SEC §3 | Plain double-submit CSRF (V) | Signed session-bound token + Origin check |
| M-15 | Med | SEC | ASVS L2 claimed without mapping (V) | SEC §15 coverage map; per-requirement audit in Phase 13 |
| M-16 | Med | EXAM §4 | Listening play limit presented as enforceable (V) | Documented as a UX control |
| M-17 | Med | SEC §2 | Suspended users keep valid access tokens (V) | Per-request status/session check with synchronous cache invalidation |
| M-18 | Med | SPK §1, §5, §8 | Latency stated as fact; LiveKit re-dispatch assumed (A) | Targets labelled; explicit backend re-dispatch; prototype verification |
| M-19 | Med | ROADMAP P2, DEVGUIDE §1, DEPLOY §3 | Phase 2 service list exceeded the minimal brief (V) | Minimal Compose set; services added per phase |
| M-20 | Med | DB | Missing constraints (turn seq, live subscription, option parent, evaluation idempotency) (V) | Added in DB §4, §6, §7 |
| M-21 | Med | SEC §11, CMS §2, AI §4 | Legal/business choices presented as defaults (V) | New open decisions D-12…D-16 |
| M-22 | Med | AI §5 | ~100 speaking samples insufficient for pronunciation calibration (A) | Validation vs calibration distinguished; band range until calibrated |
| L-01 | Low | ROADMAP | Phase 1 marked `done` (V) | `active` |
| L-02 | Low | SYS §3.1 | Audit dependency drawn for 2 modules only (V) | Declared a universal dependency |
| L-03 | Low | API §4 | SSE across replicas unspecified (V) | Redis pub/sub + Nginx buffering off + polling fallback |
| L-04 | Low | DB §3 | Account-deletion states ambiguous (V) | Deletion lifecycle defined |
| L-05 | Low | EXAM §7 | Scoring from answers would skip unanswered questions (V) | Scoring iterates the manifest |

## Items verified without changes

- All 18 objective question types from the brief are present with stable codes.
- All ADR / D- / R- references resolve. All internal Markdown links and backtick document references resolve. Phase numbers stay within 1–14 (heuristic linter, see final report).
- Content immutability and attempt pinning (ADR-007) are consistent across CMS, DB, and EXAM docs.

## Not verified (limitations)

- Mermaid diagrams were **not rendered**. No Mermaid CLI is installed, and no packages were installed (per instructions). A heuristic syntax linter found no known-bad patterns, which reduces but does not eliminate the risk of render errors.
- Vendor behaviour (LiveKit dispatch metadata, re-dispatch, webhook timing) and IELTS scoring policy details marked **A** remain assumptions until the Phase 10 prototype / official confirmation.
