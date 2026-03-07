from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from glob import glob
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ingest.providers.claude_local import adapt_claude_local_records
from ingest.providers.codex_lb_request_logs import adapt_codex_lb_request_logs
from ingest.providers.codex_lb_sqlite import adapt_codex_lb_sqlite_records
from ingest.providers.openai_codex_local import adapt_openai_codex_local_records
from storage.usage_event_store import UsageEventStore


@dataclass(frozen=True, slots=True)
class IngestSource:
    connector: str
    source_path: Path


@dataclass(frozen=True, slots=True)
class PollingConfig:
    startup_backfill_days: int = 30
    incremental_interval_seconds: int = 30
    safety_rescan_hours: int = 24
    mutable_window_days: int = 7


_DEFAULT_GLOBS: dict[str, str] = {
    "claude_local": "~/.claude/**/*.jsonl",
    "openai_codex_local": "~/.codex/**/*.jsonl",
    "codex_lb_request_logs": "~/.codex-lb/request-logs/**/*.jsonl",
    "codex_lb_sqlite": "~/.codex-lb/store.db",
}

_ADAPTERS: dict[str, Callable[..., tuple[list[Any], Any]]] = {
    "claude_local": adapt_claude_local_records,
    "openai_codex_local": adapt_openai_codex_local_records,
    "codex_lb_request_logs": adapt_codex_lb_request_logs,
    "codex_lb_sqlite": adapt_codex_lb_sqlite_records,
}

_ROW_CURSOR_CONNECTORS = {"codex_lb_sqlite"}


def discover_default_sources(max_files_per_connector: int = 20) -> list[IngestSource]:
    discovered: list[IngestSource] = []
    for connector, pattern in _DEFAULT_GLOBS.items():
        expanded_pattern = str(Path(pattern).expanduser())
        paths = sorted(Path(item) for item in glob(expanded_pattern, recursive=True))
        for path in paths[: max(max_files_per_connector, 1)]:
            if path.is_file():
                discovered.append(IngestSource(connector=connector, source_path=path))
    return discovered


def parse_sources_payload(items: Sequence[Mapping[str, Any]]) -> list[IngestSource]:
    sources: list[IngestSource] = []
    for item in items:
        connector = str(item.get("connector", "")).strip()
        source_path = str(item.get("source_path", "")).strip()
        if connector not in _ADAPTERS or not source_path:
            continue
        sources.append(
            IngestSource(
                connector=connector,
                source_path=Path(source_path).expanduser(),
            )
        )
    return sources


def _cursor_to_line(cursor_value: str | None) -> int:
    if not cursor_value:
        return 0
    if not cursor_value.startswith("line:"):
        return 0
    try:
        return max(int(cursor_value.split(":", 1)[1]), 0)
    except ValueError:
        return 0


def _line_to_cursor(line_number: int) -> str:
    return f"line:{max(line_number, 0)}"


def _cursor_to_row_id(cursor_value: str | None) -> int:
    if not cursor_value:
        return 0
    if not cursor_value.startswith("id:"):
        return 0
    try:
        return max(int(cursor_value.split(":", 1)[1]), 0)
    except ValueError:
        return 0


def _row_id_to_cursor(row_id: int) -> str:
    return f"id:{max(row_id, 0)}"


def _load_records(path: Path, *, start_line: int) -> tuple[list[str], int]:
    records: list[str] = []
    total_lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            total_lines = index + 1
            if index < start_line:
                continue
            records.append(line.rstrip("\n"))
    return records, total_lines


def _load_codex_lb_sqlite_records(
    path: Path,
    *,
    start_after_id: int,
) -> tuple[list[dict[str, Any]], int]:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                id,
                account_id,
                api_key_id,
                request_id,
                requested_at,
                model,
                input_tokens,
                output_tokens,
                cached_input_tokens,
                reasoning_tokens,
                reasoning_effort,
                latency_ms,
                status,
                error_code,
                error_message
            FROM request_logs
            WHERE id > ?
            ORDER BY id ASC
            """,
            (max(start_after_id, 0),),
        ).fetchall()
    finally:
        connection.close()

    records = [dict(row) for row in rows]
    latest_id = max(start_after_id, 0)
    if records:
        latest_id = int(records[-1].get("id") or latest_id)
    return records, latest_id


def run_ingest_cycle(
    *,
    store: UsageEventStore,
    sources: Sequence[IngestSource],
    session_project_map: Mapping[str, str] | None = None,
    workspace_project_map: Mapping[str, str] | None = None,
    path_project_map: Mapping[str, str] | None = None,
    force_rescan: bool = False,
) -> dict[str, Any]:
    checkpoints = store.ingest_status_snapshot().get("checkpoints", [])
    checkpoint_map: dict[tuple[str, str], str | None] = {}
    if isinstance(checkpoints, list):
        for item in checkpoints:
            if not isinstance(item, Mapping):
                continue
            connector = str(item.get("connector", "")).strip()
            source_key = str(item.get("source_key", "")).strip()
            cursor_value = item.get("cursor_value")
            checkpoint_map[(connector, source_key)] = (
                str(cursor_value) if isinstance(cursor_value, str) else None
            )

    summary_sources: list[dict[str, Any]] = []
    total_inserted = 0
    total_updated = 0
    total_malformed = 0
    total_parsed = 0

    for source in sources:
        connector = source.connector
        source_key = str(source.source_path)
        adapter = _ADAPTERS.get(connector)
        if adapter is None:
            continue

        start_line = 0
        start_row_id = 0
        if not force_rescan and connector in _ROW_CURSOR_CONNECTORS:
            start_row_id = _cursor_to_row_id(checkpoint_map.get((connector, source_key)))
        elif not force_rescan:
            start_line = _cursor_to_line(checkpoint_map.get((connector, source_key)))

        started_at = datetime.now(UTC)
        if not source.source_path.exists():
            store.record_ingest_run(
                connector=connector,
                source_key=source_key,
                status="error",
                source_complete=False,
                error_code="source_not_found",
                error_message=f"Missing source file: {source_key}",
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
            summary_sources.append(
                {
                    "connector": connector,
                    "source_key": source_key,
                    "status": "error",
                    "inserted_records": 0,
                    "updated_records": 0,
                    "malformed_records": 0,
                    "error_code": "source_not_found",
                }
            )
            continue

        try:
            cursor_value = _line_to_cursor(0)
            if connector in _ROW_CURSOR_CONNECTORS:
                records, latest_row_id = _load_codex_lb_sqlite_records(
                    source.source_path,
                    start_after_id=start_row_id,
                )
                cursor_value = _row_id_to_cursor(latest_row_id)
            else:
                records, total_lines = _load_records(source.source_path, start_line=start_line)
                cursor_value = _line_to_cursor(total_lines)

            events, stats = adapter(
                records,
                source_path=source_key,
                session_project_map=session_project_map,
                workspace_project_map=workspace_project_map,
                path_project_map=path_project_map,
            )
            inserted_or_updated = store.append_usage_events(events)
            inserted_records = min(inserted_or_updated, len(events))
            updated_records = max(inserted_or_updated - inserted_records, 0)
            malformed_records = int(getattr(stats, "skipped_malformed_lines", 0))
            parsed_records = int(getattr(stats, "parsed_records", len(events)))
            skipped_records = max(parsed_records - inserted_or_updated, 0)
            source_watermark = datetime.fromtimestamp(
                source.source_path.stat().st_mtime, tz=UTC
            )

            store.record_ingest_run(
                connector=connector,
                source_key=source_key,
                status="success",
                parsed_records=parsed_records,
                inserted_records=inserted_records,
                updated_records=updated_records,
                skipped_records=skipped_records,
                malformed_records=malformed_records,
                source_watermark=source_watermark,
                source_complete=True,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
            store.upsert_ingest_checkpoint(
                connector=connector,
                source_key=source_key,
                cursor_value=cursor_value,
                source_watermark=source_watermark,
                updated_at=datetime.now(UTC),
            )

            total_inserted += inserted_records
            total_updated += updated_records
            total_malformed += malformed_records
            total_parsed += parsed_records
            summary_sources.append(
                {
                    "connector": connector,
                    "source_key": source_key,
                    "status": "success",
                    "parsed_records": parsed_records,
                    "inserted_records": inserted_records,
                    "updated_records": updated_records,
                    "malformed_records": malformed_records,
                    "skipped_records": skipped_records,
                }
            )
        except Exception as error:
            store.record_ingest_run(
                connector=connector,
                source_key=source_key,
                status="error",
                source_complete=False,
                error_code="ingest_exception",
                error_message=str(error),
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
            summary_sources.append(
                {
                    "connector": connector,
                    "source_key": source_key,
                    "status": "error",
                    "inserted_records": 0,
                    "updated_records": 0,
                    "malformed_records": 0,
                    "error_code": "ingest_exception",
                    "error_message": str(error),
                }
            )

    return {
        "ran_at": datetime.now(UTC).isoformat(),
        "source_count": len(summary_sources),
        "parsed_records": total_parsed,
        "inserted_records": total_inserted,
        "updated_records": total_updated,
        "malformed_records": total_malformed,
        "sources": summary_sources,
    }
