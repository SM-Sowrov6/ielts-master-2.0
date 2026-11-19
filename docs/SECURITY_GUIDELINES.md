# IELTS MASTER 2.0 — Security Guidelines

| Field | Value |
|---|---|
| Status | **Draft v0.2 — revised after Phase 1 audit; awaiting approval** |
| Baseline | OWASP ASVS 4.x Level 2, OWASP API Security Top 10 (2023), OWASP Top 10 |
| Last updated | 2026-11-17 |

Security is reviewed **before** each API is implemented (working rule 14). Every PR touching auth, payments, file handling, or student data requires a security-checklist sign-off (§16).

---

## 1. Threat Model Summary

| Asset | Threats | Primary controls |
|---|---|---|
| Student accounts | credential stuffing, session theft, account takeover | Argon2id, rate limits, breached-password check, refresh rotation + reuse detection, MFA for staff |
| Exam integrity | answer key leakage, timer tampering, replaying submits | key-stripped student views, server timers, idempotency, state machine |
| Student data (essays, recordings, analytics) | IDOR/BOLA, over-exposure | ownership policies on every query, response schemas, signed URLs |
| Content (licensed) | scraping, bulk download | auth-gated content via attempts, rate limits, signed short-lived media, watermarking (optional) |
| AI budget | abuse, prompt injection, quota bypass | quota reservation before calls, per-user limits, injection guards |
| Payments | forged webhooks, replay | signature verification, idempotent event processing, no card data stored |
| Infrastructure | secret leakage, vulnerable deps/images | secret manager, scans in CI, least privilege |

## 2. Authentication

- **Passwords:** Argon2id (`argon2-cffi`). Initial params: memory 64 MiB, iterations 3, parallelism 1 (tuned to ~250 ms on production hardware), with automatic rehash-on-login when params change; hashing runs in a thread pool behind a concurrency limit; production refuses settings below the OWASP minimum. NFKC-normalised; length 10-128 code points. Rejected: entries of the bundled common-password blocklist (117,572 entries of 10-128 chars from SecLists `xato-net-10-million-passwords-1000000.txt` at a pinned commit, MIT License, Mark Burnett's dataset; rebuilt deterministically by `scripts/update_password_blocklist.py`, which verifies a pinned SHA-256) and passwords containing the email address/local part or the site name. No composition rules (NIST 800-63B).
- **Sessions (ADR-006, revised 2026-11-18; implemented in `app/modules/identity`):** opaque 256-bit random token in the `__Host-session` cookie (`Secure; HttpOnly; SameSite=Lax; Path=/`; a plain `ielts_session` cookie without Secure only in local/ci). The database stores the SHA-256 hash only. Lifetime 7 days idle (sliding, written at most every 5 minutes) / 30 days absolute. A new token at every login (any presented old session is revoked: no fixation) and on password change. Password change revokes all other sessions; password reset and logout-all revoke all sessions.
- **Status, roles and permissions are re-read from the database on every request**, so suspension, deletion, role changes and revocation take effect immediately (no JWT, no `roles_version`).
- **One-time tokens are never stored raw:** `raw = HMAC(key, purpose + salt)`. The token's hash and the outbox message carrying the salt are committed in one transaction, and the worker re-derives the link, so an email can never carry a token whose row failed to commit (`app/modules/identity/tokens.py`, `emails.py`). Links put the token in the URL fragment (`#token=`), which is never sent to servers or in Referer headers; the page removes it from the address bar.
- **No account enumeration:** register, resend and forgot always return the same 202; an existing owner receives an "already registered" email instead; unknown accounts are checked against a decoy hash for equal timing. Email verification and password reset are separate lifecycles (a reset never verifies an email). Unverified accounts cannot sign in (`email_not_verified` is shown only after a correct password).
- **Login protection:** progressive delay + per-account and per-IP limits, generic errors, optional CAPTCHA (Cloudflare Turnstile) after repeated failures.
- **MFA:** TOTP for staff (mandatory before production), optional for students. Recovery codes are hashed. **Status 2026-11-20: implemented for staff** (`identity/mfa.py`, migration `0013`). Wherever `STAFF_MFA_REQUIRED` is in effect (always in production) the staff gate answers `403 mfa_required` until the session passes the second factor; the admin console then shows enrolment (QR code, one confirming code, 10 single-use recovery codes) or code entry. RFC 6238 TOTP (SHA-1, 6 digits, 30 s, ±1 step), each step accepted once (replay guard), 5 attempts per 5 min per user, AES-256-GCM-encrypted secrets (key derived from `AUTH_SECRET_KEY`, so rotating it requires staff to enrol again), HMAC-hashed recovery codes, a new session token on success, every outcome audited. Lost device: `scripts/admin_cli.py reset-mfa EMAIL`. Optional student 2FA is not built.
- **OAuth:** Authorization Code + PKCE, `state` and `nonce` validated, verified email required to link accounts.
- **One-time tokens** (verify/reset) are hashed, single-use, and short-lived (verify 24 h, reset 30 min).

## 3. Session & CSRF

- Same-origin deployment (ADR-006) removes CORS from the web path. In production CORS is disabled, and in dev it is allow-listed to `localhost`.
- CSRF (implemented in `app/modules/identity/csrf.py`; applies to **every** unsafe `/api/` request including login and registration, which are bound to an "anonymous" value before sign-in; JSON bodies only; `Sec-Fetch-Site`, when sent, must be `same-origin`; `Origin`, when sent, must equal `PUBLIC_APP_URL` or a listed trusted origin): SameSite=Lax + **signed, session-bound double-submit token** (OWASP CSRF Cheat Sheet). The token is `HMAC(server_secret, session_id ‖ random)`, delivered in the `__Host-csrf` cookie and echoed in the `X-CSRF-Token` header on all POST/PUT/PATCH/DELETE with cookie auth. The server verifies the header equals the cookie **and** the HMAC binds it to the current session, which defeats cookie-injection attacks that plain double-submit is vulnerable to. It is rotated on login/refresh. Bearer-token requests are exempt. Additionally, `Origin`/`Sec-Fetch-Site` headers are checked on unsafe methods (reject cross-site).
- Webhooks (payments, LiveKit) are CSRF-exempt and authenticated by signature instead.
- Logout and password change revoke sessions server-side.

## 4. Authorization

### 4.1 RBAC

| Permission (examples) | super_admin | admin | content_manager | reviewer | student |
|---|---|---|---|---|---|
| `users.read` / `users.manage` | ✓ / ✓ | ✓ / ✓ | – | – | – |
| `roles.assign` | ✓ | ✓ (not super_admin/admin roles) | – | – | – |
| `roles.manage` | ✓ | – | – | – | – |
| `content.edit` / `content.import` / `media.upload` | ✓ | ✓ | ✓ | – | – |
| `content.review` | ✓ | ✓ | – | ✓ | – |
| `content.publish` / `content.licenses.manage` | ✓ | ✓ | – | – | – |
| `exams.configure` | ✓ | ✓ | – | – | – |
| `billing.read` / `billing.manage` | ✓ / ✓ | ✓ / – | – | – | – |
| `ai.read` / `ai.manage` | ✓ / ✓ | ✓ / – | – | – | – |
| `speaking.recordings.read` | ✓ | – (by exception, audited) | – | – | – |
| `audit.read` | ✓ | ✓ | – | – | – |
| `system.configure` | ✓ | – | – | – | – |

Permissions are data (seeded by migration). Endpoints declare required permissions via a FastAPI dependency, `require(perm("content.publish"))`. **Implemented:** `require_permission(code)`, `require_staff` (`admin.access` + staff 2FA gate) and, for every admin API, `require_staff_permission(*codes)`.

**Staff provisioning (2026-11-19, ADR-019):** staff roles, including the initial `super_admin`, are assigned only out of band with `scripts/admin_cli.py`; no HTTP endpoint grants roles and there is no staff registration. Only `active` (email-verified) accounts can be promoted; passwords are prompted without echo or read from a named environment variable (never argv), policy-checked and Argon2id-hashed; every grant/revoke revokes the account's sessions and is audited (`identity.role.granted` / `identity.role.revoked`, `via=admin_cli`); the last active super admin cannot be removed by accident. Procedure: `ADMIN_CONSOLE.md` §3.

### 4.2 Object-level authorization (BOLA/IDOR prevention)

**Implemented for attempts (2026-11-19):** every attempt query filters `user_id` (another user's attempt → 404, tested); answer writes and submit also need the writer lease (`X-Writer-Token`, stored as SHA-256). Answer keys and explanations are served only by `/attempts/{id}/review` for the owner's completed attempt; attempt content, catalogue and audio endpoints carry no keys (tested in API and in a real browser by scanning every non-review response).

- **Every student-owned query is scoped in the repository layer**: `repo.get_attempt(attempt_id, owner_id=current_user.id)`. There is no "get by id then check" pattern for student routes. Not-found and not-owned both return **404** (no existence leak).
- Staff access to student data goes through separate admin services with explicit permissions and audit entries.
- Automated tests: for every owner-scoped endpoint, a parametrised test asserts user B gets 404 on user A's resource (`TESTING_STRATEGY.md` §3.3).

### 4.3 Property-level authorization

Response models are explicit Pydantic schemas per audience (student vs admin), and ORM objects are never returned directly. Request models forbid extra fields (`model_config = ConfigDict(extra="forbid")`) to prevent mass assignment (e.g., a student setting `role` or `status`).

## 5. Input Validation & Injection

- Pydantic validation at the boundary with lengths, enums, and numeric ranges on every field. Hard size limits: JSON body 1 MB (writing 64 KB of text), uploads via presigned URLs only.
- SQL: SQLAlchemy Core/ORM with bound parameters only. Raw `text()` SQL requires review and must use bind params. Dynamic sorting uses allow-listed column maps.
- Rich text (passages, explanations): stored as ProseMirror JSON with an allow-listed node/mark schema, validated server-side. Rendered by React without `dangerouslySetInnerHTML`. Any legacy HTML import is sanitised (`nh3`) and converted.
- Student text (essays, coach messages) is rendered as plain text only.
- LLM prompt injection: see `AI_ENGINE_ARCHITECTURE.md` §10. LLM outputs are untrusted (schema-validated, rendered as text).
- SSRF: the backend never fetches arbitrary user-supplied URLs. Import from URL is not supported.

## 6. HTTP Security Headers (Nginx + Next.js)

```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{n}' 'strict-dynamic';
  style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://<cdn-host>;
  media-src 'self' blob: https://<media-host>; connect-src 'self' wss://<livekit-host> https://<sentry-ingest>;
  frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), geolocation=(), microphone=(self)
Cross-Origin-Opener-Policy: same-origin
```
Nonce-based CSP via Next.js middleware. Report-only mode runs first in staging, with violations sent to Sentry.

## 7. Rate Limiting

Redis fixed-window counters at the API (per user / per IP / per account; hashed keys only) + Cloudflare WAF rules at the edge. **Authentication endpoints fail closed** (503) when Redis is unavailable. Implemented for auth (`app/modules/identity/ratelimit.py`): login 5/min/IP + 10 failures/hour/account with progressive delay (no hard lockout); register, forgot, resend and reset 5/min/IP; verify 10/min/IP; password change 10/hour/user; emails per address 5/hour (silent, so it reveals nothing). Note: a shared IP (classroom, NAT) can reach 5/min; tune after real usage. Client IPs come from `uvicorn --proxy-headers`, trusted only from `FORWARDED_ALLOW_IPS`. Audit rows and sessions store only a truncated IP prefix (/24 IPv4, /48 IPv6).

| Route class | Limit (initial) |
|---|---|
| Auth (login/register/forgot) | 5/min/IP, 10/hour/account |
| Autosave | 10/s per attempt, burst 30 |
| General authenticated | 120/min/user |
| AI-triggering endpoints | plan quota + 10/min/user |
| Admin | 300/min/user |
| Webhooks | provider IP allow-list where published + signature |

## 8. Files & Media

- Uploads only via **presigned PUT URLs** (5 min TTL) with enforced `Content-Type`, max size, and checksum. Keys are server-generated (`{kind}/{uuid}`), never user filenames.
- Post-upload processing: magic-byte verification, allow-listed types (audio: mp3/m4a/wav/ogg; images: png/jpg/webp; documents for import: pdf/docx/json/csv), ClamAV scan, EXIF stripping, re-encoding (re-encoding neutralises many malicious payloads).
- **Status 2026-11-19:** presigned PUT (5 min), server-generated keys, MIME allow-list, size limits and post-upload verification (size, file signature, SHA-256; failure → `failed` and the object is deleted) are implemented. ClamAV scan, quarantine, EXIF stripping and re-encoding are **not**, so uploads are refused outside local/ci (`MEDIA_UPLOADS_ENABLED` cannot be enabled in staging/production). Staff playback uses 5-minute presigned GETs.
- Buckets are private. Block public access, except a separate public bucket for licence-cleared covers/marketing.
- Downloads use signed GET URLs: exam audio TTL bound to the section duration, recordings ≤ 5 min. CDN signed URLs for audio delivery at scale.

## 9. Secrets & Keys

- No secrets in the repo, images, or logs. `.env.example` only contains placeholders. `gitleaks` runs in pre-commit and CI.
- Production secrets live in a secret manager (AWS Secrets Manager / Doppler / 1Password Secrets Automation — chosen with D-05) and are injected at deploy time as environment/files with restricted permissions.
- Key rotation: JWT signing keys use `kid` and dual-key validation windows. Rotation happens quarterly and immediately on suspected compromise.
- AI provider keys are stored only on backend/voice runtimes, scoped per environment with spending limits set at the provider.
- Encryption: TLS 1.2+ everywhere (Cloudflare → Nginx → services, including the internal DB connection), with at-rest encryption for DB and buckets (managed). Application-level envelope encryption for MFA secrets and any stored OAuth tokens.

## 10. Database Least Privilege

See `DATABASE_SCHEMA.md` §11. The app role cannot run DDL, cannot UPDATE/DELETE audit logs, and has no superuser rights. Migrations run as a separate role in a one-off deploy job. The DB is reachable only from the private network.

## 11. Privacy, Consent & Data Retention

> The retention periods below are **proposed technical defaults, not approved policy**. Final values are a business/legal decision (D-12) and must be confirmed before production (Phase 13). All values are configuration, not code.

| Data | Retention (proposed default) | Deletion |
|---|---|---|
| Account & profile | Until deletion request (+14-day grace) | Hard-delete PII; pseudonymise analytics rows |
| Exam attempts & answers | Account lifetime | Deleted with account |
| Essays & writing evaluations | Account lifetime | Deleted with account |
| Speaking audio | 90 days after session (configurable per plan/consent) | Nightly purge job + bucket lifecycle rule; user can delete any time |
| Speaking transcripts & evaluations | Account lifetime | Deleted with account |
| AI request logs (metrics only) | 13 months | Pseudonymised on account deletion |
| LangSmith traces | 30 days, redacted, sampled | Provider retention setting |
| Audit logs | 2 years | Actor pseudonymised on account deletion |
| Payment records | As required by tax law (typically 6–7 years) | Retained minimal, PII-minimised |
| Server logs | 30 days | Rotation |

- Consents are versioned (`user_consents`), and changes to policy documents prompt re-consent.
- **Benchmark/training use:** student essays or recordings are **never** used for evaluation datasets or model improvement without explicit opt-in consent. They are never sent to providers that train on customer data (provider data-usage terms are reviewed per provider, with zero-retention options where available).
- **Speaking consents:** `voice_processing` (required to use speaking; live audio goes to STT/LLM/TTS processors) and `audio_recording` (optional storage), as detailed in `REALTIME_SPEAKING_ARCHITECTURE.md` §6.
- **Minors (A-4):** the technical design supports an age-confirmation step at signup, a `parental` consent record, and feature gating (e.g., recording disabled) for users below a configurable age. **The minimum age, whether parental consent is required, and its verification method are legal decisions (D-13)**, and they need legal review per target market before launch. Decided 2026-11-18: minimum age 16+, no parental consent, self-declared checkbox (configurable `REGISTRATION_MINIMUM_AGE`); Terms/Privacy (D-17) still pending, so production registration remains closed.
- Data export (FR-ID-07) produces a JSON + media archive via an async job, with a signed link valid for 24 h.
- Data-processing agreements with each AI/voice/email/payment provider are tracked in an internal register.

## 12. Payments

- No card data touches our servers. Use provider-hosted checkout (PCI SAQ-A scope).
- Webhooks: verify signature with a timestamp tolerance (≤ 5 min), store `provider_event_id` uniquely (idempotent), process asynchronously, and re-fetch object state from the provider API for critical transitions rather than trusting the payload alone.
- Subscription state changes are driven by verified events only, never by client redirects.

## 13. Logging, Audit & Monitoring

- Structured logs with PII redaction (emails hashed, tokens/passwords never logged, essay/transcript text never logged).
- `audit_logs` for: auth events (login, failed login, MFA changes, password reset), role changes, content lifecycle, admin access to student data, billing adjustments, configuration changes, data exports/deletions.
- Alerts: spikes in 401/403/404 per IP, refresh-token reuse events, admin login from a new location, webhook signature failures, AI spend anomalies.

## 14. Supply Chain & Infrastructure

- Dependencies are pinned via lockfiles (`uv.lock`, `pnpm-lock.yaml`). Renovate/Dependabot opens update PRs. `pip-audit` / `pnpm audit` / OSV-Scanner run in CI and block on high/critical.
- Containers: minimal base images (distroless/slim), non-root user, read-only root FS where possible, no package managers in the final stage. **Trivy** scans images and IaC in CI and blocks on critical.
- SAST: Semgrep (Python + TS rulesets) + Bandit. CodeQL optional.
- DAST: OWASP ZAP baseline against staging per release (Phase 12 full scan).
- GitHub: branch protection, required reviews, signed commits encouraged, OIDC for cloud credentials (no long-lived CI keys), least-privilege `GITHUB_TOKEN` permissions.
- Backups: encrypted, stored in a separate account/project, monthly restore drill (RPO/RTO in NFR-RL-03).

### 14.1 Dependency audit gates and accepted-risk register

**Gates (CI `dependency-audit` job, decided 2026-11-18):**
| Scope | Command | Gate |
|---|---|---|
| Python, all workspace packages incl. dev tools (superset of the backend image's 24 runtime packages) | `uv export --all-packages` → `pip-audit --strict` | **Blocking** |
| Node **production** dependencies | `pnpm audit --prod --audit-level high` | **Blocking. Must never be relaxed** |
| Node **development** dependencies (ESLint, Vitest, Vite, …) | `pnpm audit --dev --audit-level moderate` | Non-blocking. Full findings printed and a CI warning annotation raised. Nothing is ignored or suppressed |

**Coverage verification (2026-11-18):** every one of the 13 packages in the frontend standalone bundle is in the production dependency tree, so `--prod` audits everything the production image ships from the lockfile. **Known gaps:** (1) packages Next.js pre-compiles into `next/dist/compiled` (146, including a `picomatch` copy) are invisible to lockfile audits and are covered only by upgrading `next`. (2) OS packages in the base images are not audited until Trivy image scanning is enabled.

**Accepted risks** (temporary; each needs an owner decision, a review trigger and a review date):

| ID | Package / advisory | Severity | Dependency path(s) | Scope | Accepted | Review |
|---|---|---|---|---|---|---|
| AR-001 | `picomatch` ≤ 4.0.7, GHSA-fc5q-39xc-vjpf (ReDoS via single-branch repeated extglobs); no patched version published | High | `eslint-config-next › @next/eslint-plugin-next › fast-glob › micromatch › picomatch@2.3.2`; `vitest › vite / tinyglobby › picomatch@4.0.7` (and via typescript-eslint) | Dev tooling only. Not in the production dependency tree. Glob patterns are developer-authored, not user input | 2026-11-18 by Product Owner (Phase 4 review, option 1) | When a patched `picomatch` is released (upgrade, then close), or at the latest **2027-02-18** |
| AR-002 | `minimatch` 7.0.0–11.0.0, GHSA-g3hv-75wg-m249 (DoS via globparts amplification) | Moderate | `eslint-config-next › typescript-eslint › … › @typescript-eslint/typescript-estree › minimatch@10.2.6` | Dev tooling only (lint) | 2026-11-18 (reported since Phase 2) | When typescript-eslint ships minimatch ≥ 11.0.1, or **2027-02-18** |

Rules: an accepted risk never covers production dependencies. Closing one means upgrading and removing the row. Extending one needs a new owner decision.

## 15. OWASP ASVS L2 Coverage Map

This map shows where each ASVS 4.0.3 chapter is addressed. It is a design-level mapping. **Requirement-by-requirement verification happens in Phase 13** (audit checklist tracked in `docs/security/asvs-l2-checklist.md`, created then).

| ASVS chapter | Covered in | Notes / gaps |
|---|---|---|
| V1 Architecture & threat modelling | §1, `SYSTEM_ARCHITECTURE.md` | Threat model to be revisited per phase |
| V2 Authentication | §2 | Breached-password check, MFA for staff, Argon2id |
| V3 Session management | §2, §3 | Rotation, reuse detection, revocation, idle/absolute timeouts |
| V4 Access control | §4 | RBAC + object-level scoping, deny by default, authz test matrix |
| V5 Validation, sanitisation, encoding | §5 | Pydantic/Zod, ProseMirror allow-list, no raw HTML |
| V6 Stored cryptography | §9 | Managed at-rest encryption, envelope encryption for MFA secrets, key rotation |
| V7 Error handling & logging | §13 | problem+json without stack traces, PII redaction, audit log |
| V8 Data protection | §11 | Retention, export/deletion, cache-control on sensitive responses (`no-store`) |
| V9 Communications | §9 | TLS 1.2+ end-to-end, HSTS |
| V10 Malicious code | §14 | Dependency/image scanning, SAST, no dynamic code execution |
| V11 Business logic | `EXAMINATION_ENGINE_DESIGN.md`, §7 | Server timers, idempotency, quotas, rate limits |
| V12 Files & resources | §8 | Presigned uploads, type/size validation, AV scan, no user-controlled paths |
| V13 API & web services | §4.3, `API_SPECIFICATION.md` | Schema validation, mass-assignment protection, webhook signatures |
| V14 Configuration | §9, §14, `DEPLOYMENT_ARCHITECTURE.md` | Hardened images, security headers, secrets management |

## 16. PR Security Checklist (required for sensitive PRs)

- [ ] AuthN required? AuthZ permission declared? Ownership scoped in repository query?
- [ ] Request schema forbids extra fields; lengths/ranges bounded?
- [ ] Response schema exposes only intended fields (no keys, hashes, internal IDs)?
- [ ] Rate limit class assigned?
- [ ] Audit log written for privileged/state-changing actions?
- [ ] Secrets/config via settings only; nothing logged that shouldn't be?
- [ ] Idempotency for retried operations (webhooks, tasks, submits)?
- [ ] Tests: unauthenticated, wrong-role, wrong-owner, invalid input cases?
- [ ] File handling: presigned, validated, scanned?

## 17. Incident Response (outline)

Severity levels P1–P4. On-call rotation once in production. Runbooks for credential leak (rotate keys, revoke sessions), data exposure (contain, assess, notify per law, e.g., within 72 h where GDPR applies), and provider compromise. Post-incident reviews are blameless and documented in `docs/incidents/`.
