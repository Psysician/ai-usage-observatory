# ai-usage-observatory

Local-first observability stack for Claude and OpenAI usage with project attribution, freshness-aware metrics, and privacy-safe memory insights.

## Why This Design

This repository follows a canonical-telemetry-first model: all provider data is normalized into a shared `usage_event` ledger before attribution and analytics. Widgets and API responses then consume one audited source of truth rather than provider-specific transforms.

## Architecture Decisions (Non-Obvious)

- Project attribution is deterministic and confidence-scored instead of best-effort opaque mapping. Unknown attribution is preserved explicitly when confidence is weak.
- Cost is modeled in two layers: estimated and billed. The split avoids false precision while invoices lag upstream usage.
- Freshness and attribution quality metadata are attached to metric responses so stale or uncertain data is visible to users.
- Dashboard customization is constrained by a certified widget catalog to prevent metric-definition drift while still allowing flexible layouts.
- Storage is local-first by default, with optional redacted sync for team sharing.
- Claude memory insights are metadata/churn-first and intentionally avoid returning raw memory content.

## Invariants

- Every stored usage event must retain provider source metadata and attribution confidence metadata.
- Metric payloads must include freshness state and source timestamps.
- Memory insights must expose metadata/trend signals without raw memory text leakage.
- Certified widget definitions must remain stable even when user layouts are edited.

## Tradeoffs

- Batch-first ingestion reduces operational risk but near-real-time dashboards may lag new writes.
- Confidence-based attribution improves auditability but keeps some events in an unknown-project bucket.
- Local-first persistence improves privacy posture but team visibility requires explicit sync opt-in.

## Scope Anchors

- Multi-provider usage observability (Claude + OpenAI) with project attribution.
- Cost/token analytics with auditability signals.
- Customizable dashboard views/widgets.
- Claude memory-file insights with privacy constraints.

## Run and Verify

### Root quality gate

```bash
make test
```

### Python APIs

```bash
python3 -m pip install fastapi uvicorn
# optional: persist canonical event ledger in a custom SQLite file
export USAGE_EVENT_STORE_DB=/tmp/ai-usage-observatory/usage-events.sqlite3
uvicorn main:app --app-dir apps/observability-api/src --reload --port 8000
uvicorn main:app --app-dir apps/dashboard-api/src --reload --port 8001
```

### Runtime status endpoint

```bash
curl -s http://127.0.0.1:8000/ingest/status | jq .
```

### Trigger codex-lb SQLite import

```bash
curl -s -X POST http://127.0.0.1:8000/ingest/run \
  -H 'content-type: application/json' \
  -d '{"sources":[{"connector":"codex_lb_sqlite","source_path":"~/.codex-lb/store.db"}]}' \
  | jq .
```

### Web checks

```bash
npm --prefix apps/dashboard-web ci
npm --prefix apps/dashboard-web run typecheck
npm --prefix apps/dashboard-web run test:e2e
```
