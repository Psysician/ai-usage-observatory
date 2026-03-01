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


def _normalize_identity_fields(
    *,
    provider: str,
    project_id: str,
    model: str,
    event_time: datetime | str,
    ingested_at: datetime | str | None,
) -> dict[str, Any]:
    return {
        "event_time": _parse_datetime(event_time),
        "ingested_at": _parse_datetime(ingested_at or datetime.now(UTC)),
        "provider": provider.strip().lower(),
        "project_id": project_id.strip() or "unknown",
        "model": model.strip() or "unknown",
    }


def _normalize_numeric_fields(
    *,
    input_tokens_non_cached: Any,
    output_tokens: Any,
    cache_read_tokens: Any,
    cache_write_tokens: Any,
    reasoning_tokens: Any,
    latency_ms: Any,
    estimated_cost_usd: Any,
) -> dict[str, Any]:
    return {
        "tokens": {
            "input_tokens_non_cached": _safe_int(input_tokens_non_cached),
            "output_tokens": _safe_int(output_tokens),
            "cache_read_tokens": _safe_int(cache_read_tokens),
            "cache_write_tokens": _safe_int(cache_write_tokens),
        },
        "reasoning_tokens": (
            _safe_int(reasoning_tokens) if reasoning_tokens is not None else None
        ),
        "latency_ms": _safe_int(latency_ms) if latency_ms is not None else None,
        "estimated_cost_usd": _safe_float(estimated_cost_usd),
    }


def _build_event_identity(
    *,
    provider: str,
    source_type: str,
    source_path_or_key: str,
    source_event_id: str,
    event_time: datetime,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "source_type": source_type,
        "source_path_or_key": source_path_or_key,
        "source_event_id": source_event_id,
        "event_time": event_time.isoformat(),
    }


def _build_lineage_basis(
    *,
    event_identity: Mapping[str, Any],
    model: str,
    project_id: str,
    attribution_reason_code: str,
    attribution_confidence: float,
    request_id: str | None,
    status: str | None,
    latency_ms: int | None,
    estimated_cost_usd: float | None,
    metadata: Mapping[str, Any],
    tokens: Mapping[str, int],
    reasoning_tokens: int | None,
) -> dict[str, Any]:
    return {
        **event_identity,
        "model": model,
        "project_id": project_id,
        "attribution_reason_code": attribution_reason_code,
        "attribution_confidence": round(float(attribution_confidence), 4),
        "request_id": request_id or "",
        "status": status or "",
        "latency_ms": latency_ms if latency_ms is not None else "",
        "estimated_cost_usd": estimated_cost_usd if estimated_cost_usd is not None else "",
        "metadata": repr(sorted(metadata.items())),
        **tokens,
        "reasoning_tokens": reasoning_tokens if reasoning_tokens is not None else "",
    }


def _extract_raw_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_type": str(raw["source_type"]),
        "source_path_or_key": str(raw["source_path_or_key"]),
        "source_event_id": str(raw["source_event_id"]),
        "attribution_reason_code": str(raw["attribution_reason_code"]),
        "attribution_confidence": float(raw["attribution_confidence"]),
        "request_id": raw.get("request_id"),
        "status": raw.get("status"),
        "metadata": dict(raw.get("metadata") or {}),
    }


def _build_event_hashes(
    *,
    identity: Mapping[str, Any],
    numerics: Mapping[str, Any],
    fields: Mapping[str, Any],
) -> tuple[str, str]:
    event_identity = _build_event_identity(
        provider=identity["provider"],
        source_type=fields["source_type"],
        source_path_or_key=fields["source_path_or_key"],
        source_event_id=fields["source_event_id"],
        event_time=identity["event_time"],
    )
    lineage_basis = _build_lineage_basis(
        event_identity=event_identity,
        model=identity["model"],
        project_id=identity["project_id"],
        attribution_reason_code=fields["attribution_reason_code"],
        attribution_confidence=fields["attribution_confidence"],
        request_id=fields["request_id"],
        status=fields["status"],
        latency_ms=numerics["latency_ms"],
        estimated_cost_usd=numerics["estimated_cost_usd"],
        metadata=fields["metadata"],
        tokens=numerics["tokens"],
        reasoning_tokens=numerics["reasoning_tokens"],
    )
    return _stable_hash(event_identity), _stable_hash(lineage_basis)


def _build_usage_event(
    *,
    identity: Mapping[str, Any],
    numerics: Mapping[str, Any],
    fields: Mapping[str, Any],
    event_id: str,
    lineage_hash: str,
) -> UsageEvent:
    return UsageEvent(
        event_id=event_id,
        source_event_id=fields["source_event_id"],
        event_time=identity["event_time"],
        ingested_at=identity["ingested_at"],
        provider=identity["provider"],
        model=identity["model"],
        model_family=_model_family(identity["model"]),
        project_id=identity["project_id"],
        attribution_confidence=max(min(fields["attribution_confidence"], 1.0), 0.0),
        attribution_reason_code=fields["attribution_reason_code"].strip() or "unknown_fallback",
        input_tokens_non_cached=numerics["tokens"]["input_tokens_non_cached"],
        output_tokens=numerics["tokens"]["output_tokens"],
        cache_read_tokens=numerics["tokens"]["cache_read_tokens"],
        cache_write_tokens=numerics["tokens"]["cache_write_tokens"],
        reasoning_tokens=numerics["reasoning_tokens"],
        source_type=fields["source_type"],
        source_path_or_key=fields["source_path_or_key"],
        lineage_hash=lineage_hash,
        request_id=(
            fields["request_id"] if fields["request_id"] is None else str(fields["request_id"])
        ),
        status=fields["status"] if fields["status"] is None else str(fields["status"]),
        latency_ms=numerics["latency_ms"],
        estimated_cost_usd=numerics["estimated_cost_usd"],
        metadata=fields["metadata"],
    )


def _normalize_usage_event_from_raw(raw: Mapping[str, Any]) -> UsageEvent:
    identity = _normalize_identity_fields(
        provider=str(raw["provider"]),
        project_id=str(raw["project_id"]),
        model=str(raw["model"]),
        event_time=raw["event_time"],
        ingested_at=raw.get("ingested_at"),
    )
    numerics = _normalize_numeric_fields(
        input_tokens_non_cached=raw.get("input_tokens_non_cached", 0),
        output_tokens=raw.get("output_tokens", 0),
        cache_read_tokens=raw.get("cache_read_tokens", 0),
        cache_write_tokens=raw.get("cache_write_tokens", 0),
        reasoning_tokens=raw.get("reasoning_tokens"),
        latency_ms=raw.get("latency_ms"),
        estimated_cost_usd=raw.get("estimated_cost_usd"),
    )
    fields = _extract_raw_fields(raw)
    event_id, lineage_hash = _build_event_hashes(
        identity=identity,
        numerics=numerics,
        fields=fields,
    )
    return _build_usage_event(
        identity=identity,
        numerics=numerics,
        fields=fields,
        event_id=event_id,
        lineage_hash=lineage_hash,
    )


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
    return _normalize_usage_event_from_raw(locals())
