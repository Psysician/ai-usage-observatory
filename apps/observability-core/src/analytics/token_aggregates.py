from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

SUPPORTED_TIME_BUCKETS: tuple[str, ...] = ("hour", "day", "month")
TOKEN_FIELDS: tuple[str, ...] = (
    "input_tokens_non_cached",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bucket_start(value: datetime, time_bucket: str) -> datetime:
    if time_bucket == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if time_bucket == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if time_bucket == "month":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(
        f"Unsupported time_bucket={time_bucket!r}. Supported values: {SUPPORTED_TIME_BUCKETS}"
    )


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_attributed(project_id: Any) -> bool:
    if project_id is None:
        return False
    normalized = str(project_id).strip().lower()
    return normalized not in ("", "unknown")


def aggregate_tokens(
    events: Iterable[Mapping[str, Any]],
    *,
    time_bucket: str = "day",
    dimensions: Sequence[str] = ("provider", "project_id"),
) -> list[dict[str, Any]]:
    """
    Aggregate canonical usage events into token totals across the requested dimensions.
    """
    if time_bucket not in SUPPORTED_TIME_BUCKETS:
        raise ValueError(
            f"Unsupported time_bucket={time_bucket!r}. Supported values: {SUPPORTED_TIME_BUCKETS}"
        )

    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for event in events:
        dt = _coerce_datetime(
            event.get("event_time") or event.get("timestamp") or event.get("ingested_at")
        )
        if dt is None:
            continue
        bucket_key = _bucket_start(dt, time_bucket).isoformat()
        dimension_values = tuple(
            "unknown" if event.get(dimension) in (None, "") else str(event.get(dimension))
            for dimension in dimensions
        )
        key = (bucket_key, *dimension_values)
        if key not in grouped:
            record: dict[str, Any] = {
                "time_bucket": bucket_key,
                "events_total": 0,
                "events_attributed": 0,
            }
            for index, dimension in enumerate(dimensions):
                record[dimension] = dimension_values[index]
            for field in TOKEN_FIELDS:
                record[field] = 0
            grouped[key] = record

        current = grouped[key]
        current["events_total"] += 1
        if _is_attributed(event.get("project_id")):
            current["events_attributed"] += 1
        for field in TOKEN_FIELDS:
            current[field] += _safe_int(event.get(field), 0)

    results: list[dict[str, Any]] = []
    for key in sorted(grouped):
        record = grouped[key]
        tokens_total = sum(record[field] for field in TOKEN_FIELDS)
        record["tokens_total"] = tokens_total
        events_total = record["events_total"]
        if events_total == 0:
            coverage = 0.0
        else:
            coverage = (record["events_attributed"] / events_total) * 100.0
        record["attribution_coverage_pct"] = round(coverage, 2)
        results.append(record)
    return results


def attribution_coverage_pct(events: Iterable[Mapping[str, Any]]) -> float:
    total = 0
    attributed = 0
    for event in events:
        total += 1
        if _is_attributed(event.get("project_id")):
            attributed += 1
    if total == 0:
        return 0.0
    return round((attributed / total) * 100.0, 2)


def unknown_project_token_share_pct(events: Iterable[Mapping[str, Any]]) -> float:
    token_totals = defaultdict(int)
    for event in events:
        project_id = "unknown" if event.get("project_id") in (None, "") else str(event.get("project_id"))
        event_total = sum(_safe_int(event.get(field), 0) for field in TOKEN_FIELDS)
        token_totals["all"] += event_total
        if project_id.lower() == "unknown":
            token_totals["unknown"] += event_total
    all_tokens = token_totals["all"]
    if all_tokens <= 0:
        return 0.0
    return round((token_totals["unknown"] / all_tokens) * 100.0, 2)
