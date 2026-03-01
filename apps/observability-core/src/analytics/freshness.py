from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

FRESHNESS_STATES: tuple[str, ...] = ("live", "warm", "stale", "partial")


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


def derive_source_watermark(events: Iterable[Mapping[str, Any]]) -> str | None:
    latest: datetime | None = None
    for event in events:
        dt = _coerce_datetime(
            event.get("snapshot_at")
            or event.get("event_time")
            or event.get("timestamp")
            or event.get("ingested_at")
        )
        if dt is None:
            continue
        if latest is None or dt > latest:
            latest = dt
    if latest is None:
        return None
    return latest.isoformat()


def build_freshness_metadata(
    source_watermark: str | datetime | None,
    *,
    now: str | datetime | None = None,
    warm_after_seconds: int = 300,
    stale_after_seconds: int = 1800,
    source_complete: bool = True,
    attribution_coverage_pct: float | None = None,
) -> dict[str, Any]:
    """
    Build a normalized freshness envelope for metric payloads.
    """
    if warm_after_seconds < 0 or stale_after_seconds < 0:
        raise ValueError("Freshness thresholds must be non-negative")
    if stale_after_seconds < warm_after_seconds:
        raise ValueError("stale_after_seconds must be >= warm_after_seconds")

    now_dt = _coerce_datetime(now) or datetime.now(timezone.utc)
    watermark_dt = _coerce_datetime(source_watermark)

    quality_flags: list[str] = []
    staleness_seconds: int | None = None

    if watermark_dt is None:
        state = "partial"
        quality_flags.append("missing_source_watermark")
    else:
        delta = int((now_dt - watermark_dt).total_seconds())
        if delta < 0:
            delta = 0
            quality_flags.append("clock_skew_detected")
        staleness_seconds = delta

        if not source_complete:
            state = "partial"
            quality_flags.append("source_snapshot_incomplete")
        elif delta <= warm_after_seconds:
            state = "live"
        elif delta <= stale_after_seconds:
            state = "warm"
        else:
            state = "stale"

    if attribution_coverage_pct is not None and attribution_coverage_pct < 100.0:
        quality_flags.append("attribution_incomplete")

    return {
        "freshness_state": state,
        "source_watermark": watermark_dt.isoformat() if watermark_dt else None,
        "staleness_seconds": staleness_seconds,
        "generated_at": now_dt.isoformat(),
        "thresholds_seconds": {
            "warm_after_seconds": warm_after_seconds,
            "stale_after_seconds": stale_after_seconds,
        },
        "quality_flags": quality_flags,
    }
