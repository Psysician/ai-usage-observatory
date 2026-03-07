from __future__ import annotations

import importlib.util
import importlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
CORE_SRC = REPO_ROOT / "apps" / "observability-core" / "src"
OBS_API_SRC = REPO_ROOT / "apps" / "observability-api" / "src"
DASH_API_SRC = REPO_ROOT / "apps" / "dashboard-api" / "src"


def _ensure_path(path: Path) -> None:
    path_str = str(path)
    if path_str in sys.path:
        sys.path.remove(path_str)
    sys.path.insert(0, path_str)


def _purge_conflicting_modules(package_name: str, owner_hint: str) -> None:
    loaded = sys.modules.get(package_name)
    module_file = str(getattr(loaded, "__file__", "")) if loaded is not None else ""
    if loaded is not None and owner_hint not in module_file:
        for key in [
            name
            for name in list(sys.modules.keys())
            if name == package_name or name.startswith(f"{package_name}.")
        ]:
            del sys.modules[key]


def _load_module(module_name: str, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _seed_usage_events() -> None:
    from ingest.normalization.usage_event import normalize_usage_event
    from storage.usage_event_store import (
        append_usage_events,
        record_ingest_run,
        reset_usage_event_store,
        upsert_ingest_checkpoint,
    )

    reset_usage_event_store()
    events = [
        normalize_usage_event(
            provider="claude",
            source_type="fixture",
            source_path_or_key="tests://runtime",
            source_event_id="evt-runtime-1",
            event_time=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            model="claude-3-7-sonnet",
            project_id="project-runtime",
            attribution_confidence=0.95,
            attribution_reason_code="explicit_project_marker",
            input_tokens_non_cached=120,
            output_tokens=60,
            cache_read_tokens=10,
            cache_write_tokens=4,
            estimated_cost_usd=0.35,
        ),
        normalize_usage_event(
            provider="openai",
            source_type="fixture",
            source_path_or_key="tests://runtime",
            source_event_id="evt-runtime-2",
            event_time=datetime(2026, 3, 1, 10, 15, tzinfo=timezone.utc),
            model="gpt-4.1",
            project_id="project-runtime",
            attribution_confidence=0.90,
            attribution_reason_code="session_linkage_map",
            input_tokens_non_cached=90,
            output_tokens=40,
            cache_read_tokens=0,
            cache_write_tokens=0,
            estimated_cost_usd=0.28,
        ),
    ]
    appended = append_usage_events(events)
    assert appended == 2
    record_ingest_run(
        connector="claude_local",
        source_key="tests://runtime/claude.jsonl",
        status="success",
        parsed_records=2,
        inserted_records=2,
        malformed_records=0,
        source_watermark=datetime(2026, 3, 1, 10, 15, tzinfo=timezone.utc),
        source_complete=True,
    )
    upsert_ingest_checkpoint(
        connector="claude_local",
        source_key="tests://runtime/claude.jsonl",
        cursor_value="offset:2",
        source_watermark=datetime(2026, 3, 1, 10, 15, tzinfo=timezone.utc),
    )


def _create_codex_lb_store(db_path: Path) -> None:
    connection = sqlite3.connect(str(db_path))
    try:
        connection.executescript(
            """
            CREATE TABLE request_logs (
                id INTEGER PRIMARY KEY,
                account_id TEXT NOT NULL,
                api_key_id TEXT,
                request_id TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cached_input_tokens INTEGER,
                reasoning_tokens INTEGER,
                reasoning_effort TEXT,
                latency_ms INTEGER,
                status TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT
            );
            INSERT INTO request_logs (
                id,
                account_id,
                api_key_id,
                request_id,
                requested_at,
                model,
                input_tokens,
                output_tokens,
                cached_input_tokens,
                reasoning_tokens,
                reasoning_effort,
                latency_ms,
                status,
                error_code,
                error_message
            ) VALUES (
                1,
                'acct-runtime',
                NULL,
                'req-runtime-1',
                '2026-03-01 10:30:00.000000',
                'gpt-5.3-codex',
                120,
                42,
                100,
                8,
                NULL,
                950,
                'success',
                NULL,
                NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_runtime_http_endpoints_metrics_projects_views() -> None:
    _ensure_path(CORE_SRC)
    _ensure_path(OBS_API_SRC)

    _purge_conflicting_modules("routes", "observability-api")
    obs_main = _load_module("observability_api_runtime_main", OBS_API_SRC / "main.py")
    _seed_usage_events()

    metrics_module = importlib.import_module("routes.metrics")
    projects_module = importlib.import_module("routes.projects")
    ingest_module = importlib.import_module("routes.ingest_status")

    metrics_payload = metrics_module.get_metrics(
        time_bucket="day",
        warm_after_seconds=300,
        stale_after_seconds=1800,
    )
    assert metrics_payload["provider_split"]
    assert metrics_payload["project_split"]
    assert "source_status" in metrics_payload["auditability"]

    projects_payload = projects_module.get_projects(
        time_bucket="day",
        warm_after_seconds=300,
        stale_after_seconds=1800,
    )
    assert projects_payload["projects"]
    assert projects_payload["projects"][0]["providers"]
    assert "source_status" in projects_payload["auditability"]

    ingest_payload = ingest_module.get_ingest_status()
    assert ingest_payload["connectors"]
    assert ingest_payload["source_complete"] is True
    assert ingest_payload["source_watermark"] is not None

    ingest_run_payload = ingest_module.run_ingest(payload={"sources": []})
    assert "result" in ingest_run_payload
    assert "status" in ingest_run_payload

    _ensure_path(DASH_API_SRC)
    _purge_conflicting_modules("routes", "dashboard-api")
    dash_main = _load_module("dashboard_api_runtime_main", DASH_API_SRC / "main.py")
    assert dash_main.app is not None
    views_module = importlib.import_module("routes.views")

    create_payload = {
        "actor_user_id": "alice",
        "spec": {
            "schema_version": "1.0",
            "name": "Runtime Team View",
            "scope": "team",
            "owner": {"user_id": "alice", "role": "Editor"},
            "layout": {
                "columns": 12,
                "row_height": 32,
                "items": [{"binding_id": "widget-main", "x": 0, "y": 0, "w": 12, "h": 6}],
            },
            "filters": {"time_bucket": "day", "provider": "claude"},
            "widgets": [
                {
                    "binding_id": "widget-main",
                    "widget_id": "provider-token-split",
                    "params": {"time_bucket": "day"},
                    "overrides": {},
                }
            ],
        },
    }
    create_response = views_module.create_view(create_payload)
    view_id = create_response["view_id"]

    list_response = views_module.list_views(scope="team")
    assert any(view["view_id"] == view_id for view in list_response["views"])


def test_runtime_ingest_run_accepts_codex_lb_sqlite_source(tmp_path: Path) -> None:
    _ensure_path(CORE_SRC)
    _ensure_path(OBS_API_SRC)
    _purge_conflicting_modules("routes", "observability-api")
    _load_module("observability_api_runtime_main_sqlite", OBS_API_SRC / "main.py")
    _seed_usage_events()

    db_path = tmp_path / "codex-lb-store.db"
    _create_codex_lb_store(db_path)

    ingest_module = importlib.import_module("routes.ingest_status")
    payload = {
        "sources": [
            {
                "connector": "codex_lb_sqlite",
                "source_path": str(db_path),
            }
        ]
    }
    response = ingest_module.run_ingest(payload=payload)
    result = response["result"]
    status = response["status"]

    assert result["source_count"] == 1
    assert result["parsed_records"] == 1
    assert result["inserted_records"] == 1
    assert status["connectors"]
    checkpoint = next(
        item
        for item in status["checkpoints"]
        if item["connector"] == "codex_lb_sqlite" and item["source_key"] == str(db_path)
    )
    assert checkpoint["cursor_value"] == "id:1"
