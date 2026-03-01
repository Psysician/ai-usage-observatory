from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from ingest.attribution.project_attribution import resolve_project_attribution
from ingest.normalization.usage_event import UsageEvent, normalize_usage_event


@dataclass(frozen=True, slots=True)
class ParseStats:
    parsed_records: int
    skipped_malformed_lines: int


def _first(record: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return max(int(float(stripped)), 0)
        except ValueError:
            return default
    return default


def _parse_datetime(value: Any, fallback_index: int) -> str:
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(raw).astimezone(UTC).isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_index, tz=UTC).isoformat()


def _coerce_record(raw: str | Mapping[str, Any]) -> Mapping[str, Any] | None:
    if isinstance(raw, Mapping):
        return raw
    line = raw.strip()
    if not line:
        return None
    return json.loads(line)


def _usage_int(
    usage: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    usage_keys: tuple[str, ...],
    record_keys: tuple[str, ...],
) -> int:
    return _safe_int(
        _first(
            usage,
            *usage_keys,
            default=_first(record, *record_keys, default=0),
        )
    )


def _extract_usage_values(
    record: Mapping[str, Any],
    usage: Mapping[str, Any],
) -> dict[str, Any]:
    input_tokens = _usage_int(
        usage,
        record,
        usage_keys=("input_tokens", "prompt_tokens", "input"),
        record_keys=("input_tokens", "prompt_tokens"),
    )
    output_tokens = _usage_int(
        usage,
        record,
        usage_keys=("output_tokens", "completion_tokens", "output"),
        record_keys=("output_tokens", "completion_tokens"),
    )
    cache_read_tokens = _usage_int(
        usage,
        record,
        usage_keys=("cache_read_input_tokens", "cache_read_tokens", "cached_tokens"),
        record_keys=("cache_read_tokens", "cached_tokens"),
    )
    cache_write_tokens = _usage_int(
        usage,
        record,
        usage_keys=("cache_creation_input_tokens", "cache_write_tokens"),
        record_keys=("cache_write_tokens",),
    )
    reasoning_tokens = _first(
        usage,
        "reasoning_tokens",
        default=_first(record, "reasoning_tokens"),
    )
    return {
        "input_tokens_non_cached": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "reasoning_tokens": (
            _safe_int(reasoning_tokens) if reasoning_tokens is not None else None
        ),
    }


def _build_parsed_payload(
    record: Mapping[str, Any],
    *,
    index: int,
    token_values: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "provider": "claude",
        "source_type": "claude_local",
        "source_event_id": str(_first(record, "id", "event_id", default=f"claude-{index}")),
        "event_time": _parse_datetime(
            _first(record, "timestamp", "event_time", "created_at"),
            fallback_index=index,
        ),
        "model": str(_first(record, "model", default="claude-unknown")),
        "input_tokens_non_cached": token_values["input_tokens_non_cached"],
        "output_tokens": token_values["output_tokens"],
        "cache_read_tokens": token_values["cache_read_tokens"],
        "cache_write_tokens": token_values["cache_write_tokens"],
        "reasoning_tokens": token_values["reasoning_tokens"],
        "project_hint": _first(record, "project_id", "project"),
        "session_id": _first(record, "session_id", "conversation_id", "session"),
        "workspace_path": _first(record, "cwd", "workspace_path", "path"),
        "metadata": dict(record),
        "request_id": _first(record, "request_id"),
        "status": _first(record, "status"),
        "latency_ms": _first(record, "latency_ms"),
        "estimated_cost_usd": _first(record, "estimated_cost_usd", "cost_usd"),
    }


def parse_claude_local_records(
    records: Iterable[str | Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], ParseStats]:
    parsed: list[dict[str, Any]] = []
    malformed = 0

    for index, raw in enumerate(records):
        try:
            record = _coerce_record(raw)
        except (TypeError, json.JSONDecodeError):
            malformed += 1
            continue

        if not record:
            continue

        usage = record.get("usage", {}) if isinstance(record.get("usage"), Mapping) else {}
        token_values = _extract_usage_values(record, usage)
        parsed.append(_build_parsed_payload(record, index=index, token_values=token_values))

    return parsed, ParseStats(parsed_records=len(parsed), skipped_malformed_lines=malformed)


def adapt_claude_local_records(
    records: Iterable[str | Mapping[str, Any]],
    *,
    source_path: str,
    session_project_map: Mapping[str, str] | None = None,
    workspace_project_map: Mapping[str, str] | None = None,
    path_project_map: Mapping[str, str] | None = None,
    ingested_at: datetime | None = None,
) -> tuple[list[UsageEvent], ParseStats]:
    parsed, stats = parse_claude_local_records(records)
    events: list[UsageEvent] = []

    for payload in parsed:
        attribution = resolve_project_attribution(
            explicit_project_id=payload.get("project_hint"),
            session_id=payload.get("session_id"),
            source_path=source_path,
            workspace_path=payload.get("workspace_path"),
            metadata=payload.get("metadata"),
            session_project_map=session_project_map,
            workspace_project_map=workspace_project_map,
            path_project_map=path_project_map,
        )

        events.append(
            normalize_usage_event(
                provider=payload["provider"],
                source_type=payload["source_type"],
                source_path_or_key=source_path,
                source_event_id=payload["source_event_id"],
                event_time=payload["event_time"],
                model=payload["model"],
                project_id=attribution.project_id,
                attribution_confidence=attribution.confidence,
                attribution_reason_code=attribution.reason_code,
                input_tokens_non_cached=payload["input_tokens_non_cached"],
                output_tokens=payload["output_tokens"],
                cache_read_tokens=payload["cache_read_tokens"],
                cache_write_tokens=payload["cache_write_tokens"],
                reasoning_tokens=payload["reasoning_tokens"],
                request_id=payload.get("request_id"),
                status=str(payload["status"]) if payload.get("status") is not None else None,
                latency_ms=payload.get("latency_ms"),
                estimated_cost_usd=payload.get("estimated_cost_usd"),
                metadata={"attribution_evidence": attribution.evidence, **payload["metadata"]},
                ingested_at=ingested_at or datetime.now(UTC),
            )
        )

    return events, stats
