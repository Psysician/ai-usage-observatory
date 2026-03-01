from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

CORE_SRC = Path(__file__).resolve().parents[3] / "observability-core" / "src"
if CORE_SRC.exists() and str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover - optional runtime dependency in this MVP repo
    APIRouter = None

from memory.claude_memory_scanner import ProjectResolver, build_scan_snapshot
from memory.memory_churn_metrics import build_memory_churn_metrics
from memory.memory_fact_index import build_memory_fact_index

_FRESHNESS_ORDER = {
    "live": 0,
    "warm": 1,
    "stale": 2,
    "partial": 3,
}

router = APIRouter() if APIRouter is not None else None


def _worst_freshness(states: Sequence[str]) -> str:
    if not states:
        return "partial"
    return max(states, key=lambda state: _FRESHNESS_ORDER.get(state, _FRESHNESS_ORDER["partial"]))


def _freshness_metadata(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    files = snapshot.get("files", [])
    if not isinstance(files, list):
        files = []

    freshness_states = [str(file_fact.get("freshness_state", "partial")) for file_fact in files]
    unavailable = [
        file_fact for file_fact in files if str(file_fact.get("scan_status", "error")) != "ok"
    ]

    latest_mtime = max(
        (
            float(file_fact.get("mtime_epoch_seconds"))
            for file_fact in files
            if file_fact.get("mtime_epoch_seconds") is not None
        ),
        default=None,
    )
    scan_time = float(snapshot.get("captured_at_epoch_seconds", 0.0))
    staleness_seconds = None
    if latest_mtime is not None:
        staleness_seconds = max(scan_time - latest_mtime, 0.0)

    error_codes = sorted(
        {
            str(file_fact.get("scan_error_code"))
            for file_fact in unavailable
            if file_fact.get("scan_error_code")
        }
    )

    return {
        "captured_at_epoch_seconds": scan_time,
        "freshness_state": _worst_freshness(freshness_states),
        "total_files": len(files),
        "unavailable_files": len(unavailable),
        "staleness_seconds": staleness_seconds,
        "error_codes": error_codes,
    }


def get_memory_insights(
    memory_file_paths: Sequence[str | Path],
    history_snapshots: Sequence[Mapping[str, Any]] | None = None,
    project_resolver: ProjectResolver | None = None,
    scan_time: datetime | None = None,
) -> dict[str, Any]:
    current_snapshot = build_scan_snapshot(
        memory_file_paths=memory_file_paths,
        project_resolver=project_resolver,
        scan_time=scan_time,
    )

    snapshots: list[Mapping[str, Any]] = list(history_snapshots or [])
    snapshots.append(current_snapshot)

    project_index = build_memory_fact_index(snapshots)
    churn_payload = build_memory_churn_metrics(project_index)
    freshness = _freshness_metadata(current_snapshot)

    return {
        "projects": churn_payload["projects"],
        "freshness": freshness,
        "snapshot": current_snapshot,
    }


if router is not None:  # pragma: no cover - exercised when FastAPI is available

    @router.post("/memory/insights")
    def memory_insights_endpoint(payload: Mapping[str, Any]) -> dict[str, Any]:
        memory_file_paths = payload.get("memory_file_paths", [])
        if not isinstance(memory_file_paths, list):
            memory_file_paths = []

        history_snapshots = payload.get("history_snapshots", [])
        if not isinstance(history_snapshots, list):
            history_snapshots = []

        return get_memory_insights(
            memory_file_paths=memory_file_paths,
            history_snapshots=history_snapshots,
        )
