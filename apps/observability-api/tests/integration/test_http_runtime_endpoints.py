from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient

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
    from storage.usage_event_store import append_usage_events, reset_usage_event_store

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


def test_runtime_http_endpoints_metrics_projects_views() -> None:
    _ensure_path(CORE_SRC)
    _ensure_path(OBS_API_SRC)

    _purge_conflicting_modules("routes", "observability-api")
    obs_main = _load_module("observability_api_runtime_main", OBS_API_SRC / "main.py")
    _seed_usage_events()

    obs_client = TestClient(obs_main.app)
    metrics_response = obs_client.get("/metrics", params={"time_bucket": "day"})
    assert metrics_response.status_code == 200
    metrics_payload = metrics_response.json()
    assert metrics_payload["provider_split"]
    assert metrics_payload["project_split"]

    projects_response = obs_client.get("/projects", params={"time_bucket": "day"})
    assert projects_response.status_code == 200
    projects_payload = projects_response.json()
    assert projects_payload["projects"]
    assert projects_payload["projects"][0]["providers"]

    _ensure_path(DASH_API_SRC)
    _purge_conflicting_modules("routes", "dashboard-api")
    dash_main = _load_module("dashboard_api_runtime_main", DASH_API_SRC / "main.py")
    dash_client = TestClient(dash_main.app)

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
    create_response = dash_client.post("/views", json=create_payload)
    assert create_response.status_code == 200
    view_id = create_response.json()["view_id"]

    list_response = dash_client.get("/views", params={"scope": "team"})
    assert list_response.status_code == 200
    assert any(view["view_id"] == view_id for view in list_response.json()["views"])
