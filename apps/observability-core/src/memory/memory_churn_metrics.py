from __future__ import annotations

from typing import Any, Mapping


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


def _growth_direction(delta: int) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _growth_rate_pct(delta: int, baseline: int) -> float:
    if baseline > 0:
        return round((delta / baseline) * 100.0, 2)
    if delta > 0:
        return 100.0
    if delta < 0:
        return -100.0
    return 0.0


def build_memory_churn_metrics(
    project_index: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    projects: list[dict[str, Any]] = []

    for project_id in sorted(project_index.keys()):
        points = sorted(
            project_index[project_id],
            key=lambda point: _to_float(point.get("captured_at_epoch_seconds"), default=0.0),
        )
        if not points:
            continue

        baseline_bytes = _to_int(points[0].get("total_bytes"), default=0)
        latest_bytes = _to_int(points[-1].get("total_bytes"), default=0)
        bytes_delta = latest_bytes - baseline_bytes

        changed_files_total = sum(
            _to_int(point.get("changed_files"), default=0) for point in points[1:]
        )

        first_epoch = _to_float(points[0].get("captured_at_epoch_seconds"), default=0.0)
        last_epoch = _to_float(points[-1].get("captured_at_epoch_seconds"), default=0.0)
        elapsed_seconds = max(last_epoch - first_epoch, 1.0)
        cadence_per_day = round(changed_files_total / (elapsed_seconds / 86400.0), 3)

        trend: list[dict[str, Any]] = []
        for point in points:
            trend.append(
                {
                    "captured_at_epoch_seconds": _to_float(
                        point.get("captured_at_epoch_seconds"), default=0.0
                    ),
                    "file_count": _to_int(point.get("file_count"), default=0),
                    "total_bytes": _to_int(point.get("total_bytes"), default=0),
                    "bytes_delta": _to_int(point.get("bytes_delta"), default=0),
                    "changed_files": _to_int(point.get("changed_files"), default=0),
                    "unavailable_file_count": _to_int(
                        point.get("unavailable_file_count"), default=0
                    ),
                    "freshness_state": str(point.get("freshness_state", "partial")),
                }
            )

        projects.append(
            {
                "project_id": project_id,
                "trend": trend,
                "growth": {
                    "bytes_delta": bytes_delta,
                    "growth_rate_pct": _growth_rate_pct(bytes_delta, baseline_bytes),
                    "direction": _growth_direction(bytes_delta),
                },
                "churn": {
                    "changed_files_total": changed_files_total,
                    "update_cadence_per_day": cadence_per_day,
                },
                "freshness_state": str(points[-1].get("freshness_state", "partial")),
            }
        )

    return {"projects": projects}
