from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CORE_SRC = Path(__file__).resolve().parents[3] / "observability-core" / "src"
if CORE_SRC.exists() and str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from analytics.cost_layers import (  # type: ignore  # pylint: disable=import-error
    compute_cost_layers,
    get_cost_layer_labels,
)
from analytics.freshness import (  # type: ignore  # pylint: disable=import-error
    build_freshness_metadata,
    derive_source_watermark,
)
from analytics.token_aggregates import (  # type: ignore  # pylint: disable=import-error
    SUPPORTED_TIME_BUCKETS,
    aggregate_tokens,
    attribution_coverage_pct,
    unknown_project_token_share_pct,
)

try:
    from fastapi import APIRouter, HTTPException, Query
except Exception:  # pragma: no cover - fallback for minimal environments
    class APIRouter:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.routes: list[tuple[str, str, Any]] = []

        def get(self, path: str, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                self.routes.append(("GET", path, func))
                return func

            return decorator

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def Query(default: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        return default


router = APIRouter(prefix="", tags=["projects"])


def _validate_time_bucket(time_bucket: str) -> None:
    if time_bucket not in SUPPORTED_TIME_BUCKETS:
        raise ValueError(
            f"Unsupported time_bucket={time_bucket!r}. Supported values: {SUPPORTED_TIME_BUCKETS}"
        )


def _load_events_from_store() -> list[dict[str, Any]]:
    candidates: Sequence[tuple[str, str]] = (
        ("storage.usage_event_store", "list_usage_events"),
        ("storage.usage_event_store", "get_usage_events"),
        ("ingest.usage_event_store", "list_usage_events"),
        ("ingest.usage_event_store", "get_usage_events"),
    )
    for module_name, function_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        loader = getattr(module, function_name, None)
        if loader is None or not callable(loader):
            continue
        try:
            rows = loader()
        except Exception:
            continue
        if rows is None:
            return []
        return [dict(item) for item in rows]
    return []


def _load_store_freshness_snapshot() -> dict[str, Any] | None:
    candidates: Sequence[tuple[str, str]] = (
        ("storage.usage_event_store", "get_store_freshness_snapshot"),
        ("storage.usage_event_store", "get_ingest_status_snapshot"),
    )
    for module_name, function_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        loader = getattr(module, function_name, None)
        if loader is None or not callable(loader):
            continue
        try:
            snapshot = loader()
        except Exception:
            continue
        if not isinstance(snapshot, Mapping):
            continue
        return dict(snapshot)
    return None


def _merge_token_and_cost_rows(
    token_rows: list[dict[str, Any]],
    cost_rows: list[dict[str, Any]],
    dimensions: Sequence[str],
) -> list[dict[str, Any]]:
    cost_index: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in cost_rows:
        key = (row["time_bucket"], *[row[dimension] for dimension in dimensions])
        cost_index[key] = row

    merged: list[dict[str, Any]] = []
    for token_row in token_rows:
        key = (token_row["time_bucket"], *[token_row[dimension] for dimension in dimensions])
        cost_row = cost_index.get(key)
        record = dict(token_row)
        if cost_row is None:
            labels = get_cost_layer_labels()
            record["cost_layers"] = [
                {"layer": "estimated", "label": labels["estimated"], "amount_usd": 0.0},
                {"layer": "billed", "label": labels["billed"], "amount_usd": None},
            ]
            record["cost_variance_usd"] = None
            record["missing_billed_data"] = True
        else:
            record["cost_layers"] = cost_row["cost_layers"]
            record["cost_variance_usd"] = cost_row["cost_variance_usd"]
            record["missing_billed_data"] = cost_row["missing_billed_data"]
        merged.append(record)
    return merged


def build_projects_payload(
    *,
    time_bucket: str = "day",
    events: Iterable[Mapping[str, Any]] | None = None,
    source_watermark: str | datetime | None = None,
    now: str | datetime | None = None,
    warm_after_seconds: int = 300,
    stale_after_seconds: int = 1800,
    source_complete: bool = True,
) -> dict[str, Any]:
    _validate_time_bucket(time_bucket)
    rows = [dict(item) for item in (events if events is not None else _load_events_from_store())]
    store_snapshot: dict[str, Any] | None = None
    effective_source_watermark = source_watermark
    effective_source_complete = source_complete
    if events is None:
        store_snapshot = _load_store_freshness_snapshot()
        if store_snapshot is not None:
            if effective_source_watermark is None:
                effective_source_watermark = store_snapshot.get("source_watermark")
            effective_source_complete = bool(
                store_snapshot.get("source_complete", effective_source_complete)
            )

    project_token_rows = aggregate_tokens(
        rows, time_bucket=time_bucket, dimensions=("project_id",)
    )
    project_cost_rows = compute_cost_layers(
        rows, time_bucket=time_bucket, dimensions=("project_id",)
    )
    project_totals = _merge_token_and_cost_rows(
        project_token_rows, project_cost_rows, ("project_id",)
    )

    project_provider_tokens = aggregate_tokens(
        rows, time_bucket=time_bucket, dimensions=("project_id", "provider")
    )
    project_provider_costs = compute_cost_layers(
        rows, time_bucket=time_bucket, dimensions=("project_id", "provider")
    )
    project_provider_split = _merge_token_and_cost_rows(
        project_provider_tokens, project_provider_costs, ("project_id", "provider")
    )

    indexed: dict[str, dict[str, Any]] = {}
    for row in project_totals:
        project_id = str(row["project_id"])
        indexed[project_id] = {
            "project_id": project_id,
            "time_bucket": row["time_bucket"],
            "tokens_total": row["tokens_total"],
            "attribution_coverage_pct": row["attribution_coverage_pct"],
            "cost_layers": row["cost_layers"],
            "cost_variance_usd": row["cost_variance_usd"],
            "missing_billed_data": row["missing_billed_data"],
            "providers": [],
        }

    for row in project_provider_split:
        project_id = str(row["project_id"])
        if project_id not in indexed:
            continue
        indexed[project_id]["providers"].append(
            {
                "provider": row["provider"],
                "time_bucket": row["time_bucket"],
                "tokens_total": row["tokens_total"],
                "attribution_coverage_pct": row["attribution_coverage_pct"],
                "cost_layers": row["cost_layers"],
                "cost_variance_usd": row["cost_variance_usd"],
                "missing_billed_data": row["missing_billed_data"],
            }
        )

    coverage_pct = attribution_coverage_pct(rows)
    freshness = build_freshness_metadata(
        effective_source_watermark or derive_source_watermark(rows),
        now=now,
        warm_after_seconds=warm_after_seconds,
        stale_after_seconds=stale_after_seconds,
        source_complete=effective_source_complete,
        attribution_coverage_pct=coverage_pct,
    )

    return {
        "time_bucket": time_bucket,
        "supported_time_buckets": list(SUPPORTED_TIME_BUCKETS),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects": [indexed[key] for key in sorted(indexed)],
        "auditability": {
            "freshness": freshness,
            "attribution_coverage_pct": coverage_pct,
            "unknown_project_share_pct": unknown_project_token_share_pct(rows),
            "cost_layer_labels": get_cost_layer_labels(),
            "source_status": {
                "source_complete": effective_source_complete,
                "source_watermark": freshness.get("source_watermark"),
                "connectors": (
                    list(store_snapshot.get("connectors", []))
                    if isinstance(store_snapshot, Mapping)
                    else []
                ),
            },
        },
    }


@router.get("/projects")
def get_projects(
    time_bucket: str = Query("day", description="Aggregation bucket: hour|day|month"),
    warm_after_seconds: int = Query(300, ge=0),
    stale_after_seconds: int = Query(1800, ge=0),
) -> dict[str, Any]:
    try:
        return build_projects_payload(
            time_bucket=time_bucket,
            warm_after_seconds=warm_after_seconds,
            stale_after_seconds=stale_after_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
