# Milestones: AI Usage Observatory

Version: 0.1
Date: March 1, 2026

## 1. Delivery Strategy
- Sequence: ingestion foundation -> analytics correctness -> memory insights -> customization platform -> UX + sync hardening.
- Cadence assumption: 2-week iterations.
- Priority rule: trust and auditability before UI richness.

## 2. Setup Phase (S-000)
Objective: create implementable project skeleton and team workflow.

Deliverables:
- Monorepo bootstrap (`apps/observability-core`, `apps/observability-api`, `apps/dashboard-api`, `apps/dashboard-web`, `apps/dashboard-sync`).
- Shared schema package for canonical events and widget/view contracts.
- Local dev profile and seeded fixture dataset.
- CI baseline (lint, type-check, unit tests, integration smoke).

Exit criteria:
- Local environment spins up all services.
- Seed data loads and one sample dashboard renders.
- CI green on baseline checks.

## 3. Milestone M-001: Unified Event Ingestion and Attribution
Objective: ingest Claude/OpenAI telemetry into canonical usage ledger with attribution confidence.

Scope:
- Source adapters for Claude local/ccusage and OpenAI/Codex local logs.
- Canonical `usage_event` normalization.
- Deterministic project attribution ladder + reason codes.
- Append-only event storage and dedupe.

Acceptance criteria:
- Aggregates match source totals within tolerance.
- Every event has provider + project or `unknown` with confidence.
- Replay ingest is idempotent.

Primary risks:
- Attribution false positives.
- Duplicate token accounting from source patterns.

## 4. Milestone M-002: Cost/Token/Freshness Analytics Engine
Objective: produce decision-grade analytics APIs with explicit uncertainty.

Scope:
- Estimated cost layer from versioned rate cards.
- Billed cost layer ingestion/reconciliation interface.
- Provider/project/model/time aggregate APIs.
- Freshness and quality envelope on all metric responses.

Acceptance criteria:
- API exposes estimated and billed cost fields separately.
- Freshness state propagates correctly under stale-source simulation.
- Unknown attribution share is available in project/provider endpoints.

Primary risks:
- Cost variance confusion.
- Missing billed data in early periods.

## 5. Milestone M-003: Claude Memory Insight Pipeline
Objective: add privacy-safe memory-file observability.

Scope:
- Scanner for memory metadata (file size, change frequency, staleness).
- Project-level memory insight aggregates.
- Memory insight API endpoints.

Acceptance criteria:
- No raw memory text persisted in analytics store.
- Memory trend metrics available by project.
- Scan failures surface via freshness/quality metadata.

Primary risks:
- Privacy regressions.
- Overinterpretation of memory correlations.

## 6. Milestone M-004: Declarative Custom Views and Widget Contracts
Objective: implement fully customizable dashboard platform with governance.

Scope:
- Declarative view schema (layout, filters, widgets, ownership).
- Certified widget catalog and validation rules.
- Query resolver from widget spec to analytics API.
- Saved views (personal/team/org).

Acceptance criteria:
- Users can create/update/clone views reliably.
- Shared views enforce certified widget constraints.
- View specs round-trip without data loss.

Primary risks:
- Schema instability.
- Metric drift from unconstrained customization.

## 7. Milestone M-005: Dashboard Workspace UX and Optional Team Sync
Objective: complete end-user dashboard experience and collaboration path.

Scope:
- Drag/resize grid editor and widget shells.
- Global and local filters with deep-link URL state.
- Freshness and attribution confidence visuals in every widget.
- Optional redacted sync for sharing views across team environments.

Acceptance criteria:
- End-to-end layout editing persists and reloads correctly.
- Sync exports pass redaction policy checks.
- Accessibility baseline passes keyboard navigation checks.

Primary risks:
- UI performance with high widget counts.
- Sync leakage of local identifiers without strict policy.

## 8. Cross-Cutting Gates
- Accuracy gate: aggregate totals match source truth windows.
- Trust gate: every chart shows freshness and uncertainty semantics where relevant.
- Privacy gate: memory pipeline and sync payloads pass redaction tests.
- Performance gate: dashboard load and interaction budgets met.

## 9. Suggested Timeline (10-14 weeks)
- Weeks 1-2: S-000 setup.
- Weeks 3-4: M-001.
- Weeks 5-6: M-002.
- Weeks 7-8: M-003.
- Weeks 9-11: M-004.
- Weeks 12-14: M-005 stabilization and release candidate.

## 10. Definition of Done (Program Level)
- MVP questions answered in <30 seconds from UI:
  - "How many tokens/cost for Claude vs OpenAI in project X this month?"
  - "What changed week-over-week and why?"
  - "Are memory files stale or growing abnormally for project X?"
- Shared dashboards run with governed certified metrics and explicit data-quality indicators.
