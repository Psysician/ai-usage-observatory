from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from ingest.normalization.usage_event import UsageEvent
from ingest.providers.codex_lb_request_logs import (
    ParseStats,
    adapt_codex_lb_request_logs,
)


def _map_sqlite_row(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "request_id": record.get("request_id"),
        "timestamp": record.get("requested_at"),
        "model": record.get("model"),
        "prompt_tokens": record.get("input_tokens"),
        "completion_tokens": record.get("output_tokens"),
        "cached_prompt_tokens": record.get("cached_input_tokens"),
        "reasoning_tokens": record.get("reasoning_tokens"),
        "reasoning_effort": record.get("reasoning_effort"),
        "latency_ms": record.get("latency_ms"),
        "status": record.get("status"),
        "error_code": record.get("error_code"),
        "error_message": record.get("error_message"),
        "account_id": record.get("account_id"),
        "api_key_id": record.get("api_key_id"),
    }


def adapt_codex_lb_sqlite_records(
    records: Iterable[Mapping[str, Any]],
    *,
    source_path: str,
    session_project_map: Mapping[str, str] | None = None,
    workspace_project_map: Mapping[str, str] | None = None,
    path_project_map: Mapping[str, str] | None = None,
    ingested_at: datetime | None = None,
) -> tuple[list[UsageEvent], ParseStats]:
    mapped_records = [_map_sqlite_row(record) for record in records]
    return adapt_codex_lb_request_logs(
        mapped_records,
        source_path=source_path,
        session_project_map=session_project_map,
        workspace_project_map=workspace_project_map,
        path_project_map=path_project_map,
        ingested_at=ingested_at,
    )
