# PRD: AI Usage Observatory

Version: 0.1
Date: March 1, 2026
Status: Draft for implementation

## 1. Product Summary
AI Usage Observatory is a local-first analytics product for AI coding workflows. It unifies usage telemetry from Claude and OpenAI/Codex, attributes spend and tokens to project-level slices, adds Claude memory-file analytics, and provides a fully customizable dashboard for individual developers and teams.

## 2. Problem Statement
Current workflows split usage visibility across separate tools and log formats. This creates four issues:
- Teams cannot reliably answer "how much Claude vs OpenAI did project X consume?"
- Cost and token numbers are hard to reconcile because sources differ in structure and freshness.
- Memory behavior in Claude Code is not observable in a privacy-safe operational way.
- Existing dashboards are either rigid or too flexible without governance, causing metric drift.

## 3. Goals
- Provide trusted, auditable Claude/OpenAI usage analytics by project, provider, model, and time.
- Support dual cost semantics: estimated now, billed when reconciled.
- Surface Claude memory-file insights without exposing raw memory text.
- Deliver a fully customizable dashboard with saved views, role presets, and governance guardrails.
- Keep local-first operation as the default with optional redacted team sync.

## 4. Non-Goals
- Building a stream-first distributed analytics platform for v1.
- Inferring causal productivity impact from memory analytics in v1.
- Replacing provider billing systems.
- Indexing raw private memory content for semantic search by default.

## 5. Users and Jobs To Be Done
## 5.1 Primary users
- Individual developer: "I need to understand my spend and token trends by project quickly."
- Team lead: "I need project-level provider allocation and anomaly visibility."
- FinOps/engineering manager: "I need budget tracking, variance analysis, and chargeback-grade exports."

## 5.2 Secondary users
- Platform/admin owner: "I need trustworthy ingestion health, lineage, and policy controls."

## 6. Key User Stories
- As a developer, I can filter to one project and instantly see Claude vs OpenAI token/cost split.
- As a team lead, I can view model mix and detect spend spikes by project.
- As a FinOps user, I can compare estimated vs billed costs with explicit variance.
- As an admin, I can inspect attribution confidence and freshness for every chart.
- As a power user, I can compose custom dashboards from certified widgets and save/share views.
- As a privacy-conscious user, I can analyze Claude memory-file activity without exposing memory text.

## 7. Functional Requirements
## 7.1 Ingestion and normalization
- MUST ingest Claude usage data and OpenAI/Codex usage data from local sources.
- MUST normalize source-specific payloads into a canonical usage event schema.
- MUST deduplicate known repeated token events where source formats cause duplication.

## 7.2 Project attribution
- MUST support deterministic project attribution ladder:
  - explicit project markers
  - session/conversation linkage
  - path/workspace mapping
  - unknown fallback
- MUST record attribution confidence score and reason code per event.

## 7.3 Cost and token analytics
- MUST provide token breakdown by provider/model/project/time.
- MUST provide cost breakdown by token class (input/output/cache read/cache write/reasoning if available).
- MUST publish estimated and billed cost as separate metrics.
- SHOULD provide cost delta decomposition (volume vs mix vs unit cost).

## 7.4 Freshness and auditability
- MUST expose freshness metadata (source watermark, staleness classification, last successful ingest).
- MUST expose attribution coverage and unknown share.
- MUST include lineage/provenance in metric payloads.

## 7.5 Claude memory-file analytics
- MUST scan Claude memory file metadata (count, size, mtime, churn windows).
- MUST not expose raw memory text by default.
- SHOULD expose topic/tag summaries only if generated from privacy-safe metadata extraction.

## 7.6 Dashboard customization
- MUST provide widget-based drag/resize layout editor.
- MUST support global filters and per-widget overrides.
- MUST support saved views (personal/team/org scope).
- MUST support certified widget catalog and versioned view specs.
- SHOULD support dashboard JSON import/export.

## 7.7 Collaboration and governance
- SHOULD provide role presets (`Admin`, `Editor`, `Analyst`, `Viewer`, `FinanceViewer`).
- SHOULD provide optional redacted team sync for shared dashboards.
- SHOULD provide comments/annotations and rollback for shared views.

## 8. Non-Functional Requirements
- Accuracy: aggregate totals should match source totals within defined tolerance.
- Performance: dashboard initial load <= 2.5s on typical local dataset.
- Reliability: ingestion failures are isolated and visible; partial data is explicitly labeled.
- Security/Privacy: local-first storage default; redacted sync payloads; no raw memory text default.
- Accessibility: keyboard-operable layout and filters; contrast-compliant chart themes.

## 9. KPIs and Success Metrics
- Attribution coverage >= 95% for events in active projects.
- Data freshness SLA: >= 95% of widgets in `Live` or `Warm` state.
- Dashboard time-to-answer for primary questions < 30 seconds median.
- Estimated vs billed variance transparency: 100% of cost widgets labeled with source type.
- Weekly active saved views per team as adoption indicator.

## 10. Risks and Mitigations
- Attribution false positives.
  - Mitigation: confidence scoring, reason codes, unknown bucket, manual overrides.
- Cost confusion from estimated vs billed mismatch.
  - Mitigation: dual-layer display and variance panels.
- Customization-driven metric drift.
  - Mitigation: certified metrics for shared/org views and lineage metadata.
- Privacy exposure via memory data.
  - Mitigation: metadata-only pipeline by default; strict redaction policies.

## 11. Release Scope
## 11.1 MVP (v1.0)
- Multi-provider ingestion and canonical event store.
- Project/provider/model/time token-cost analytics.
- Freshness and attribution confidence in API and UI.
- Claude memory metadata analytics.
- Custom dashboard layouts with saved views.

## 11.2 Post-MVP (v1.1+)
- Advanced anomaly detection and alert routing.
- Billed-cost reconciliation automation.
- Team-level governance workflows and policy engine.
- Richer collaboration primitives.

## 12. Open Questions
- Preferred billing reconciliation cadence for teams with monthly invoice cycles.
- Target deployment profile for sync service (self-hosted vs managed).
- Hard limits for number of widgets per dashboard for performance guardrails.
