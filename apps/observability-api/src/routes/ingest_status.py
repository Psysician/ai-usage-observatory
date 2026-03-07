from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

CORE_SRC = Path(__file__).resolve().parents[3] / "observability-core" / "src"
if CORE_SRC.exists() and str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover - fallback for minimal environments
    class APIRouter:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.routes: list[tuple[str, str, Any]] = []

        def get(self, path: str, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                self.routes.append(("GET", path, func))
                return func

            return decorator

        def post(self, path: str, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                self.routes.append(("POST", path, func))
                return func

            return decorator


router = APIRouter(prefix="", tags=["ingest"])


def _load_ingest_snapshot() -> dict[str, Any]:
    candidates: Sequence[tuple[str, str]] = (
        ("storage.usage_event_store", "get_ingest_status_snapshot"),
        ("storage.usage_event_store", "get_store_freshness_snapshot"),
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
        if isinstance(snapshot, Mapping):
            return dict(snapshot)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_watermark": None,
        "source_complete": False,
        "connectors": [],
        "checkpoints": [],
    }


def _run_ingest_cycle(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        storage_module = importlib.import_module("storage.usage_event_store")
        runner_module = importlib.import_module("ingest.local_ingest_runner")
    except Exception as error:
        return {
            "ran_at": datetime.now(UTC).isoformat(),
            "source_count": 0,
            "parsed_records": 0,
            "inserted_records": 0,
            "updated_records": 0,
            "malformed_records": 0,
            "sources": [],
            "status": "unavailable",
            "error": str(error),
        }

    store_getter = getattr(storage_module, "get_default_event_store", None)
    discover_default_sources = getattr(runner_module, "discover_default_sources", None)
    parse_sources_payload = getattr(runner_module, "parse_sources_payload", None)
    run_ingest_cycle = getattr(runner_module, "run_ingest_cycle", None)
    if not callable(store_getter) or not callable(run_ingest_cycle):
        return {
            "ran_at": datetime.now(UTC).isoformat(),
            "source_count": 0,
            "parsed_records": 0,
            "inserted_records": 0,
            "updated_records": 0,
            "malformed_records": 0,
            "sources": [],
            "status": "unavailable",
            "error": "Ingest runtime modules are missing required functions.",
        }

    body = dict(payload)
    source_entries = body.get("sources")
    sources: list[Any] = []
    if isinstance(source_entries, list) and callable(parse_sources_payload):
        sources = parse_sources_payload(
            [item for item in source_entries if isinstance(item, Mapping)]
        )
    elif callable(discover_default_sources):
        sources = discover_default_sources()

    force_rescan = bool(body.get("force_rescan", False))
    session_project_map = (
        dict(body.get("session_project_map"))
        if isinstance(body.get("session_project_map"), Mapping)
        else None
    )
    workspace_project_map = (
        dict(body.get("workspace_project_map"))
        if isinstance(body.get("workspace_project_map"), Mapping)
        else None
    )
    path_project_map = (
        dict(body.get("path_project_map"))
        if isinstance(body.get("path_project_map"), Mapping)
        else None
    )

    return run_ingest_cycle(
        store=store_getter(),
        sources=sources,
        session_project_map=session_project_map,
        workspace_project_map=workspace_project_map,
        path_project_map=path_project_map,
        force_rescan=force_rescan,
    )


@router.get("/ingest/status")
def get_ingest_status() -> dict[str, Any]:
    snapshot = _load_ingest_snapshot()
    snapshot.setdefault("generated_at", datetime.now(UTC).isoformat())
    snapshot.setdefault("source_watermark", None)
    snapshot.setdefault("source_complete", False)
    snapshot.setdefault("connectors", [])
    snapshot.setdefault("checkpoints", [])
    return snapshot


@router.post("/ingest/run")
def run_ingest(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body = dict(payload or {})
    result = _run_ingest_cycle(body)
    return {
        "result": result,
        "status": _load_ingest_snapshot(),
    }
