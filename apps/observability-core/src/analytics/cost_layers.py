from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

SUPPORTED_TIME_BUCKETS: tuple[str, ...] = ("hour", "day", "month")
COST_LAYER_LABELS: dict[str, str] = {
    "estimated": "Estimated Cost (USD)",
    "billed": "Billed Cost (USD)",
}


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_cost_layer_labels() -> dict[str, str]:
    return dict(COST_LAYER_LABELS)


def compute_cost_layers(
    events: Iterable[Mapping[str, Any]],
    *,
    time_bucket: str = "day",
    dimensions: Sequence[str] = ("provider", "project_id"),
) -> list[dict[str, Any]]:
    """
    Aggregate estimated and billed cost layers with explicit labels and variance.
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
                "estimated_usd": 0.0,
                "billed_usd": 0.0,
                "has_billed_values": False,
                "missing_billed_data": False,
            }
            for index, dimension in enumerate(dimensions):
                record[dimension] = dimension_values[index]
            grouped[key] = record

        current = grouped[key]
        current["estimated_usd"] += _safe_float(event.get("cost_estimated_usd"), 0.0)
        billed = event.get("cost_billed_usd")
        if billed is None:
            current["missing_billed_data"] = True
        else:
            current["billed_usd"] += _safe_float(billed, 0.0)
            current["has_billed_values"] = True

    results: list[dict[str, Any]] = []
    for key in sorted(grouped):
        record = grouped[key]
        estimated = round(record["estimated_usd"], 6)
        billed = round(record["billed_usd"], 6) if record["has_billed_values"] else None
        variance = round(billed - estimated, 6) if billed is not None else None

        payload: dict[str, Any] = {
            "time_bucket": record["time_bucket"],
            "cost_layers": [
                {
                    "layer": "estimated",
                    "label": COST_LAYER_LABELS["estimated"],
                    "amount_usd": estimated,
                },
                {
                    "layer": "billed",
                    "label": COST_LAYER_LABELS["billed"],
                    "amount_usd": billed,
                },
            ],
            "cost_variance_usd": variance,
            "missing_billed_data": bool(record["missing_billed_data"] or billed is None),
        }
        for dimension in dimensions:
            payload[dimension] = record[dimension]
        results.append(payload)
    return results
