from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Mapping


def _parse_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _model_family(model: str) -> str:
    trimmed = model.strip()
    if not trimmed:
        return "unknown"
    if "/" in trimmed:
        trimmed = trimmed.split("/")[-1]
    separators = ("-", ":")
    family = trimmed
    for separator in separators:
        if separator in family:
            family = family.split(separator, 1)[0]
            break
    return family or "unknown"


def _stable_hash(payload: Mapping[str, Any]) -> str:
    rendered = "|".join(f"{k}={payload[k]}" for k in sorted(payload))
    return sha256(rendered.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class UsageEvent:
    event_id: str
    source_event_id: str
    event_time: datetime
    ingested_at: datetime
    provider: str
    model: str
    model_family: str
    project_id: str
    attribution_confidence: float
    attribution_reason_code: str
    input_tokens_non_cached: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int | None
    source_type: str
    source_path_or_key: str
    lineage_hash: str
    request_id: str | None = None
    status: str | None = None
    latency_ms: int | None = None
    estimated_cost_usd: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens_total(self) -> int:
        return (
            self.input_tokens_non_cached
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + (self.reasoning_tokens or 0)
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event_time"] = self.event_time.isoformat()
        payload["ingested_at"] = self.ingested_at.isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UsageEvent":
        return cls(
            event_id=str(payload["event_id"]),
            source_event_id=str(payload["source_event_id"]),
            event_time=_parse_datetime(payload["event_time"]),
            ingested_at=_parse_datetime(payload["ingested_at"]),
            provider=str(payload["provider"]),
            model=str(payload["model"]),
            model_family=str(payload["model_family"]),
            project_id=str(payload["project_id"]),
            attribution_confidence=float(payload["attribution_confidence"]),
            attribution_reason_code=str(payload["attribution_reason_code"]),
            input_tokens_non_cached=_safe_int(payload.get("input_tokens_non_cached")),
            output_tokens=_safe_int(payload.get("output_tokens")),
            cache_read_tokens=_safe_int(payload.get("cache_read_tokens")),
            cache_write_tokens=_safe_int(payload.get("cache_write_tokens")),
            reasoning_tokens=(
                _safe_int(payload.get("reasoning_tokens"))
                if payload.get("reasoning_tokens") is not None
                else None
            ),
            source_type=str(payload["source_type"]),
            source_path_or_key=str(payload["source_path_or_key"]),
            lineage_hash=str(payload["lineage_hash"]),
            request_id=(
                str(payload["request_id"]) if payload.get("request_id") is not None else None
            ),
            status=str(payload["status"]) if payload.get("status") is not None else None,
            latency_ms=(
                _safe_int(payload.get("latency_ms"))
                if payload.get("latency_ms") is not None
                else None
            ),
            estimated_cost_usd=_safe_float(payload.get("estimated_cost_usd")),
            metadata=dict(payload.get("metadata", {})),
        )


def normalize_usage_event(
    *,
    provider: str,
    source_type: str,
    source_path_or_key: str,
    source_event_id: str,
    event_time: datetime | str,
    model: str,
    project_id: str,
    attribution_confidence: float,
    attribution_reason_code: str,
    input_tokens_non_cached: Any = 0,
    output_tokens: Any = 0,
    cache_read_tokens: Any = 0,
    cache_write_tokens: Any = 0,
    reasoning_tokens: Any = None,
    request_id: str | None = None,
    status: str | None = None,
    latency_ms: Any = None,
    estimated_cost_usd: Any = None,
    ingested_at: datetime | str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> UsageEvent:
    normalized_event_time = _parse_datetime(event_time)
    normalized_ingested_at = _parse_datetime(ingested_at or datetime.now(UTC))
    normalized_provider = provider.strip().lower()
    normalized_project = project_id.strip() or "unknown"
    normalized_model = model.strip() or "unknown"

    tokens = {
        "input_tokens_non_cached": _safe_int(input_tokens_non_cached),
        "output_tokens": _safe_int(output_tokens),
        "cache_read_tokens": _safe_int(cache_read_tokens),
        "cache_write_tokens": _safe_int(cache_write_tokens),
    }
    normalized_reasoning = (
        _safe_int(reasoning_tokens) if reasoning_tokens is not None else None
    )
    normalized_latency = _safe_int(latency_ms) if latency_ms is not None else None
    normalized_cost = _safe_float(estimated_cost_usd)
    normalized_metadata = dict(metadata or {})

    event_identity = {
        "provider": normalized_provider,
        "source_type": source_type,
        "source_path_or_key": source_path_or_key,
        "source_event_id": source_event_id,
        "event_time": normalized_event_time.isoformat(),
    }
    lineage_basis = {
        **event_identity,
        "model": normalized_model,
        "project_id": normalized_project,
        "attribution_reason_code": attribution_reason_code,
        "attribution_confidence": round(float(attribution_confidence), 4),
        "request_id": request_id or "",
        "status": status or "",
        "latency_ms": normalized_latency if normalized_latency is not None else "",
        "estimated_cost_usd": normalized_cost if normalized_cost is not None else "",
        "metadata": repr(sorted(normalized_metadata.items())),
        **tokens,
        "reasoning_tokens": normalized_reasoning if normalized_reasoning is not None else "",
    }
    event_id = _stable_hash(event_identity)
    lineage_hash = _stable_hash(lineage_basis)

    return UsageEvent(
        event_id=event_id,
        source_event_id=source_event_id,
        event_time=normalized_event_time,
        ingested_at=normalized_ingested_at,
        provider=normalized_provider,
        model=normalized_model,
        model_family=_model_family(normalized_model),
        project_id=normalized_project,
        attribution_confidence=max(min(float(attribution_confidence), 1.0), 0.0),
        attribution_reason_code=attribution_reason_code.strip() or "unknown_fallback",
        input_tokens_non_cached=tokens["input_tokens_non_cached"],
        output_tokens=tokens["output_tokens"],
        cache_read_tokens=tokens["cache_read_tokens"],
        cache_write_tokens=tokens["cache_write_tokens"],
        reasoning_tokens=normalized_reasoning,
        source_type=source_type,
        source_path_or_key=source_path_or_key,
        lineage_hash=lineage_hash,
        request_id=request_id,
        status=status,
        latency_ms=normalized_latency,
        estimated_cost_usd=normalized_cost,
        metadata=normalized_metadata,
    )

