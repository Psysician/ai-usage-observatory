# Architecture: AI Usage Observatory

Version: 0.1
Date: March 1, 2026

## 1. Architectural Goals
- Unify Claude and OpenAI/Codex telemetry in one canonical ledger.
- Attribute usage to projects with explicit confidence and reason codes.
- Separate estimated and billed costs to avoid false precision.
- Enable privacy-safe Claude memory-file analytics.
- Support fully customizable dashboards with governance controls.
- Default to local-first operation with optional redacted sync.

## 2. High-Level Topology
## 2.1 Core services
- `observability-core`: ingestion, normalization, attribution, cost/memory analytics.
- `observability-api`: metrics and drilldown APIs for usage, cost, freshness, memory.
- `dashboard-api`: view specs, widget catalog, query resolver, sharing policies.
- `dashboard-web`: customizable dashboard UI.
- `dashboard-sync` (optional): redacted shared-view synchronization.

## 2.2 Data stores
- Local primary store: DuckDB or SQLite for canonical events and aggregates.
- Local metadata store: view specs, widget settings, preferences, policies.
- Optional remote store (sync mode): Postgres/ClickHouse for shared team views.

## 3. Canonical Data Model
## 3.1 `fact_usage_event`
Required fields:
- `event_id` (stable dedupe key)
- `event_time`, `ingested_at`
- `provider` (`claude`, `openai`)
- `model`, `model_family`
- `project_id` (`unknown` allowed)
- `attribution_confidence` (0-1)
- `attribution_reason_code`
- `input_tokens_non_cached`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `reasoning_tokens` (nullable)
- `source_type`, `source_path_or_key`
- `lineage_hash`

## 3.2 Cost layers
- `fact_cost_estimate`: computed from versioned rate cards.
- `fact_cost_billed`: imported/reconciled from provider cost reports.
- `fact_cost_adjustment`: correction entries and late reconciliations.

## 3.3 Memory analytics
- `fact_memory_file_activity`:
  - `project_id`, `file_path_hash`, `file_size_bytes`, `mtime`, `scan_time`
  - churn windows (`bytes_delta_1d`, `bytes_delta_7d`, `updates_7d`)
  - `scan_status`, `scan_error_code`
- Raw memory text is out of analytics scope by default.

## 4. Ingestion Architecture
## 4.1 Source adapters
- Claude local/ccusage adapter.
- OpenAI/Codex local session adapter.
- Optional codex-lb request log adapter.

## 4.2 Pipeline stages
1. Read source snapshots/tails.
2. Parse source payloads and dedupe.
3. Normalize to canonical event schema.
4. Project attribution ladder resolution.
5. Persist append-only canonical events.
6. Update aggregate/materialized metric tables.

## 4.3 Idempotency and late events
- Idempotent ingest key = source identity + stable event fingerprint.
- Mutable time window for backfill (e.g., last 7-30 days).
- Closed windows receive explicit adjustment records.

## 5. Project Attribution Design
Attribution ladder order:
1. Explicit project marker from source.
2. Session/conversation linkage map.
3. Workspace/path mapping.
4. Heuristic mapping (git remote/path overlap/time correlation).
5. Unknown fallback.

For every event:
- Persist chosen method.
- Persist confidence score.
- Persist evidence summary for audit traces.

## 6. Cost Engine Design
- Versioned rate cards keyed by provider/model/meter/effective time range.
- Compute `estimated_cost` continuously from token counters.
- Ingest billed/reconciled costs when available.
- Expose both layers and variance metrics in every cost API.

## 7. Freshness and Data Quality
Every API payload includes:
- `freshness_state`: `live | warm | stale | partial`
- `source_watermark`
- `staleness_seconds`
- `attribution_coverage`
- `quality_flags` (e.g., missing billed layer, parser fallback used)

## 8. Dashboard System Architecture
## 8.1 View model
- Dashboard = declarative JSON spec:
  - layout grid
  - widgets
  - global filters
  - per-widget overrides
  - scope/permissions

## 8.2 Widget model
- Certified widget catalog for shared dashboards.
- Parameter schema validation per widget type.
- Query resolver translates widget specs to canonical analytics queries.
- Provenance payload attached to widget responses.

## 8.3 Customization guardrails
- Certified metrics required for team/org shared views.
- Personal views may include experimental widgets.
- Versioned view specs with migration hooks.

## 9. Security and Privacy
- Local-first default with filesystem-bound data ownership.
- Sensitive identifiers hashed/redacted in optional sync payloads.
- No raw Claude memory text in default analytics store or API.
- Role-based access for shared deployments.

## 10. Recommended Tech Baseline
- Backend API: Python FastAPI.
- Core analytics: Python + DuckDB (local) or Postgres/ClickHouse (shared).
- Web UI: React + TypeScript with grid-layout engine.
- Background jobs: simple scheduler/worker (cron or built-in orchestrator).

## 11. Known Tradeoffs
- Batch-first is simpler and safer but less real-time than stream-first.
- Confidence-based attribution is transparent but preserves unknown buckets.
- Full customization increases complexity; guardrails prevent metric drift.

## 12. References
- [OpenAI pricing](https://openai.com/api/pricing/)
- [OpenAI prompt caching](https://platform.openai.com/docs/guides/prompt-caching)
- [OpenAI usage/cost API cookbook](https://cookbook.openai.com/examples/completions_usage_api)
- [Anthropic Usage & Cost API](https://docs.anthropic.com/en/api/usage-cost-api)
- [Claude Code memory docs](https://docs.anthropic.com/en/docs/claude-code/memory)
- [Grafana dashboard variables](https://grafana.com/docs/grafana/latest/dashboards/variables/)
