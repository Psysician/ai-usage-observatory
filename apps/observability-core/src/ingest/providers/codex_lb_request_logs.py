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


def _infer_provider(record: Mapping[str, Any]) -> str:
    explicit = str(_first(record, "provider", default="")).strip().lower()
    if explicit in {"openai", "claude"}:
        return explicit
    model = str(_first(record, "model", default="")).strip().lower()
    if model.startswith("claude"):
        return "claude"
    return "openai"


def parse_codex_lb_request_logs(
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

        input_tokens = _safe_int(
            _first(
                record,
                "prompt_tokens",
                "input_tokens",
                "input",
                default=0,
            )
        )
        output_tokens = _safe_int(
            _first(
                record,
                "completion_tokens",
                "output_tokens",
                "output",
                default=0,
            )
        )
        cache_read_tokens = _safe_int(
            _first(
                record,
                "cached_prompt_tokens",
                "cache_read_tokens",
                "cached_tokens",
                default=0,
            )
        )
        cache_write_tokens = _safe_int(_first(record, "cache_write_tokens", default=0))
        reasoning_tokens = _first(record, "reasoning_tokens")

        parsed.append(
            {
                "provider": _infer_provider(record),
                "source_type": "codex_lb_request_logs",
                "source_event_id": str(
                    _first(
                        record,
                        "request_id",
                        "id",
                        "event_id",
                        default=f"codex-lb-{index}",
                    )
                ),
                "event_time": _parse_datetime(
                    _first(record, "timestamp", "created_at", "event_time"),
                    fallback_index=index,
                ),
                "model": str(_first(record, "model", default="openai-unknown")),
                "input_tokens_non_cached": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
                "reasoning_tokens": _safe_int(reasoning_tokens) if reasoning_tokens is not None else None,
                "project_hint": _first(record, "project_id", "project"),
                "session_id": _first(record, "session_id", "conversation_id"),
                "workspace_path": _first(record, "cwd", "workspace_path", "path"),
                "metadata": dict(record),
                "request_id": _first(record, "request_id"),
                "status": _first(record, "status"),
                "latency_ms": _first(record, "latency_ms"),
                "estimated_cost_usd": _first(record, "cost_usd", "estimated_cost_usd"),
            }
        )

    return parsed, ParseStats(parsed_records=len(parsed), skipped_malformed_lines=malformed)


def adapt_codex_lb_request_logs(
    records: Iterable[str | Mapping[str, Any]],
    *,
    source_path: str,
    session_project_map: Mapping[str, str] | None = None,
    workspace_project_map: Mapping[str, str] | None = None,
    path_project_map: Mapping[str, str] | None = None,
    ingested_at: datetime | None = None,
) -> tuple[list[UsageEvent], ParseStats]:
    parsed, stats = parse_codex_lb_request_logs(records)
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

