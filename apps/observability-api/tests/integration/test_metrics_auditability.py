from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
API_SRC = REPO_ROOT / "apps" / "observability-api" / "src"
CORE_SRC = REPO_ROOT / "apps" / "observability-core" / "src"
for path in (API_SRC, CORE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _purge_conflicting_modules(package_name: str) -> None:
    loaded = sys.modules.get(package_name)
    module_file = str(getattr(loaded, "__file__", "")) if loaded is not None else ""
    if loaded is not None and "observability-api" not in module_file:
        for key in [
            name
            for name in list(sys.modules.keys())
            if name == package_name or name.startswith(f"{package_name}.")
        ]:
            del sys.modules[key]


_purge_conflicting_modules("routes")

from analytics.cost_layers import COST_LAYER_LABELS
from routes.metrics import build_metrics_payload
from routes.projects import build_projects_payload


def _seed_events(now: datetime) -> list[dict[str, object]]:
    return [
        {
            "event_time": (now - timedelta(minutes=30)).isoformat(),
            "provider": "claude",
            "project_id": "project-alpha",
            "input_tokens_non_cached": 100,
            "output_tokens": 60,
            "cache_read_tokens": 20,
            "cache_write_tokens": 5,
            "reasoning_tokens": 10,
            "cost_estimated_usd": 0.42,
            "cost_billed_usd": 0.40,
        },
        {
            "event_time": (now - timedelta(hours=2)).isoformat(),
            "provider": "openai",
            "project_id": "project-beta",
            "input_tokens_non_cached": 180,
            "output_tokens": 140,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "cost_estimated_usd": 0.80,
            "cost_billed_usd": 0.84,
        },
        {
            "event_time": (now - timedelta(days=1)).isoformat(),
            "provider": "claude",
            "project_id": "unknown",
            "input_tokens_non_cached": 80,
            "output_tokens": 35,
            "cache_read_tokens": 5,
            "cache_write_tokens": 0,
            "reasoning_tokens": 4,
            "cost_estimated_usd": 0.22,
            "cost_billed_usd": None,
        },
    ]


def test_metrics_exposes_provider_and_project_splits_for_supported_buckets() -> None:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    events = _seed_events(now)

    for bucket in ("hour", "day", "month"):
        payload = build_metrics_payload(
            time_bucket=bucket,
            events=events,
            now=now,
            warm_after_seconds=60,
            stale_after_seconds=300,
        )
        assert payload["time_bucket"] == bucket
        assert payload["supported_time_buckets"] == ["hour", "day", "month"]
        assert payload["provider_split"]
        assert payload["project_split"]

        providers = {row["provider"] for row in payload["provider_split"]}
        projects = {row["project_id"] for row in payload["project_split"]}
        assert {"claude", "openai"} <= providers
        assert {"project-alpha", "project-beta", "unknown"} <= projects


def test_cost_layers_have_clear_labels_and_missing_billed_flag() -> None:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    payload = build_metrics_payload(
        time_bucket="day",
        events=_seed_events(now),
        now=now,
        warm_after_seconds=60,
        stale_after_seconds=300,
    )

    labels = payload["auditability"]["cost_layer_labels"]
    assert labels == COST_LAYER_LABELS

    for row in payload["provider_split"] + payload["project_split"]:
        layer_map = {layer["layer"]: layer for layer in row["cost_layers"]}
        assert set(layer_map.keys()) == {"estimated", "billed"}
        assert layer_map["estimated"]["label"] == COST_LAYER_LABELS["estimated"]
        assert layer_map["billed"]["label"] == COST_LAYER_LABELS["billed"]

    unknown_row = next(row for row in payload["project_split"] if row["project_id"] == "unknown")
    assert unknown_row["missing_billed_data"] is True


def test_freshness_state_changes_when_watermark_ages_past_threshold() -> None:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    events = _seed_events(now)

    recent = build_metrics_payload(
        time_bucket="day",
        events=events,
        now=now,
        source_watermark=(now - timedelta(seconds=45)).isoformat(),
        warm_after_seconds=60,
        stale_after_seconds=300,
    )
    stale = build_metrics_payload(
        time_bucket="day",
        events=events,
        now=now,
        source_watermark=(now - timedelta(seconds=900)).isoformat(),
        warm_after_seconds=60,
        stale_after_seconds=300,
    )

    recent_state = recent["auditability"]["freshness"]["freshness_state"]
    stale_state = stale["auditability"]["freshness"]["freshness_state"]
    assert recent_state == "live"
    assert stale_state == "stale"
    assert stale_state != recent_state


def test_projects_payload_includes_auditability_fields() -> None:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    payload = build_projects_payload(
        time_bucket="month",
        events=_seed_events(now),
        now=now,
        warm_after_seconds=60,
        stale_after_seconds=300,
    )

    assert payload["projects"]
    assert "freshness" in payload["auditability"]
    assert "attribution_coverage_pct" in payload["auditability"]
    assert "cost_layer_labels" in payload["auditability"]
    assert payload["auditability"]["cost_layer_labels"] == COST_LAYER_LABELS

    for project in payload["projects"]:
        layer_map = {layer["layer"]: layer for layer in project["cost_layers"]}
        assert layer_map["estimated"]["label"] == COST_LAYER_LABELS["estimated"]
        assert layer_map["billed"]["label"] == COST_LAYER_LABELS["billed"]
