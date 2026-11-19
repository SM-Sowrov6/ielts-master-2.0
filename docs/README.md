# IELTS MASTER 2.0 — Documentation Index

Status: **Phase 1 drafts v0.2 (revised after audit), awaiting approval.** Audit record: [reviews/PHASE_1_REVIEW.md](reviews/PHASE_1_REVIEW.md). Read in this order:

| # | Document | Purpose |
|---|---|---|
| 1 | [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md) | Scope, functional & non-functional requirements, open decisions |
| 2 | [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Architectural style, repo structure, module boundaries, ADRs |
| 3 | [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Logical schema, ER diagrams, indexing, migrations |
| 4 | [API_SPECIFICATION.md](API_SPECIFICATION.md) | API conventions and endpoint inventory |
| 5 | [SECURITY_GUIDELINES.md](SECURITY_GUIDELINES.md) | Threat model, auth, authz, privacy, supply chain |
| 6 | [CONTENT_MANAGEMENT_ARCHITECTURE.md](CONTENT_MANAGEMENT_ARCHITECTURE.md) | Licensing, versioning, CMS workflow, imports, media |
| 7 | [QUESTION_BANK_DESIGN.md](QUESTION_BANK_DESIGN.md) | Question types, handler/renderer registry, scoring rules |
| 8 | [EXAMINATION_ENGINE_DESIGN.md](EXAMINATION_ENGINE_DESIGN.md) | Attempts, timers, autosave, submission, scoring |
| 9 | [AI_ENGINE_ARCHITECTURE.md](AI_ENGINE_ARCHITECTURE.md) | Providers, LangGraph workflows, evaluation quality, cost |
| 10 | [REALTIME_SPEAKING_ARCHITECTURE.md](REALTIME_SPEAKING_ARCHITECTURE.md) | LiveKit voice pipeline, examiner, recordings |
| 11 | [LEARNING_ANALYTICS_DESIGN.md](LEARNING_ANALYTICS_DESIGN.md) | Aggregates, metrics, recommendations, study plans |
| 12 | [DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md) | Topology, CI/CD, observability, DR |
| 13 | [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Test layers, gates, AI evaluation, load, security tests |
| 14 | [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) | Conventions, git workflow, PRs, Definition of Done |
| 15 | [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) | Phases, acceptance criteria, risks |
| 16 | [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md) | Tokens, components, shells, API/query conventions, a11y testing (Phase 4) |
| 17 | [ADMIN_CONSOLE.md](ADMIN_CONSOLE.md) | Super Admin console foundation: access workflow, staff provisioning, admin API authorization, dashboard |

Cross-references use stable IDs: `FR-*` / `NFR-*` (requirements), `ADR-*` (ADR-001…020, in `SYSTEM_ARCHITECTURE.md` §8), `D-*` (open decisions D-01…16, in `PROJECT_REQUIREMENTS.md` §9), `R-*` (risks, in `DEVELOPMENT_ROADMAP.md` §4).
