from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

_FRESHNESS_ORDER = {
    "live": 0,
    "warm": 1,
    "stale": 2,
    "partial": 3,
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _snapshot_epoch(snapshot: Mapping[str, Any]) -> float:
    for key in ("captured_at_epoch_seconds", "captured_at", "scan_time_epoch_seconds"):
        if key in snapshot:
            return _to_float(snapshot[key], default=0.0)
    return 0.0


def _worst_freshness(states: Iterable[str]) -> str:
    worst = "live"
    for state in states:
        value = _FRESHNESS_ORDER.get(state, _FRESHNESS_ORDER["partial"])
        if value >= _FRESHNESS_ORDER.get(worst, _FRESHNESS_ORDER["partial"]):
            worst = state if state in _FRESHNESS_ORDER else "partial"
    return worst


def build_memory_fact_index(
    snapshots: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    previous_states: dict[str, dict[str, tuple[int, str, float | None]]] = {}

    ordered_snapshots = sorted(snapshots, key=_snapshot_epoch)
    for snapshot in ordered_snapshots:
        captured_at = _snapshot_epoch(snapshot)
        files = snapshot.get("files", [])
        if not isinstance(files, list):
            continue

        project_to_facts: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for file_fact in files:
            if not isinstance(file_fact, Mapping):
                continue
            project_id = str(file_fact.get("project_id", "unknown"))
            project_to_facts[project_id].append(file_fact)

        for project_id, facts in project_to_facts.items():
            ok_facts = [fact for fact in facts if fact.get("scan_status") == "ok"]
            total_bytes = sum(_to_int(fact.get("file_size_bytes"), 0) for fact in ok_facts)
            file_count = len(ok_facts)
            unavailable_file_count = len(facts) - file_count
            latest_mtime = max(
                (_to_float(fact.get("mtime_epoch_seconds"), 0.0) for fact in ok_facts),
                default=0.0,
            )
            latest_mtime_or_none = latest_mtime if latest_mtime > 0.0 else None

            current_state: dict[str, tuple[int, str, float | None]] = {}
            for fact in facts:
                path_hash = str(fact.get("file_path_hash", ""))
                size = _to_int(fact.get("file_size_bytes"), 0)
                status = str(fact.get("scan_status", "error"))
                mtime = fact.get("mtime_epoch_seconds")
                mtime_value = _to_float(mtime, default=0.0) if mtime is not None else None
                current_state[path_hash] = (size, status, mtime_value)

            previous_state = previous_states.get(project_id)
            if previous_state is None:
                changed_files = 0
                bytes_delta = 0
            else:
                keys = set(previous_state) | set(current_state)
                changed_files = sum(
                    1 for key in keys if previous_state.get(key) != current_state.get(key)
                )
                previous_total = sum(
                    size for size, status, _ in previous_state.values() if status == "ok"
                )
                bytes_delta = total_bytes - previous_total

            freshness_state = _worst_freshness(
                str(fact.get("freshness_state", "partial")) for fact in facts
            )

            index[project_id].append(
                {
                    "project_id": project_id,
                    "captured_at_epoch_seconds": captured_at,
                    "file_count": file_count,
                    "total_bytes": total_bytes,
                    "unavailable_file_count": unavailable_file_count,
                    "changed_files": changed_files,
                    "bytes_delta": bytes_delta,
                    "latest_mtime_epoch_seconds": latest_mtime_or_none,
                    "freshness_state": freshness_state,
                }
            )

            previous_states[project_id] = current_state

    return dict(index)
