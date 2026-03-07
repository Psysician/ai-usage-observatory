from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from ingest.normalization.usage_event import UsageEvent


@dataclass(frozen=True, slots=True)
class AggregateRow:
    time_bucket: datetime
    provider: str
    project_id: str
    event_count: int
    input_tokens_non_cached: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    tokens_total: int

    def to_dict(self) -> dict[str, object]:
        return {
            "time_bucket": self.time_bucket.isoformat(),
            "provider": self.provider,
            "project_id": self.project_id,
            "event_count": self.event_count,
            "input_tokens_non_cached": self.input_tokens_non_cached,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "tokens_total": self.tokens_total,
        }


class UsageEventStore:
    def __init__(
        self,
        *,
        sqlite_path: str | Path | None = None,
        backing_file: str | Path | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._sqlite_path = self._normalize_sqlite_path(sqlite_path)
        self._backing_file = Path(backing_file) if backing_file else None
        self._connection = sqlite3.connect(self._sqlite_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

        if self._backing_file and self._backing_file.exists() and self._is_empty():
            self._import_legacy_jsonl(self._backing_file)

    def _normalize_sqlite_path(self, sqlite_path: str | Path | None) -> str:
        if sqlite_path is None:
            return _default_sqlite_path()
        if str(sqlite_path) == ":memory:":
            return ":memory:"
        expanded = Path(sqlite_path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        return str(expanded)

    def _initialize_schema(self) -> None:
        with self._connection:
            if self._sqlite_path != ":memory:":
                self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    event_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    source_event_id TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    model_family TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    attribution_confidence REAL NOT NULL,
                    attribution_reason_code TEXT NOT NULL,
                    input_tokens_non_cached INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cache_read_tokens INTEGER NOT NULL,
                    cache_write_tokens INTEGER NOT NULL,
                    reasoning_tokens INTEGER,
                    source_type TEXT NOT NULL,
                    source_path_or_key TEXT NOT NULL,
                    lineage_hash TEXT NOT NULL,
                    request_id TEXT,
                    status TEXT,
                    latency_ms INTEGER,
                    estimated_cost_usd REAL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (event_id, revision)
                );

                CREATE TABLE IF NOT EXISTS usage_event_heads (
                    event_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    lineage_hash TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_usage_events_time
                    ON usage_events(event_time);
                CREATE INDEX IF NOT EXISTS idx_usage_events_provider_project_time
                    ON usage_events(provider, project_id, event_time);

                CREATE TABLE IF NOT EXISTS ingest_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    connector TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parsed_records INTEGER NOT NULL DEFAULT 0,
                    inserted_records INTEGER NOT NULL DEFAULT 0,
                    updated_records INTEGER NOT NULL DEFAULT 0,
                    skipped_records INTEGER NOT NULL DEFAULT 0,
                    malformed_records INTEGER NOT NULL DEFAULT 0,
                    source_watermark TEXT,
                    source_complete INTEGER NOT NULL DEFAULT 1,
                    error_code TEXT,
                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_ingest_runs_connector_source
                    ON ingest_runs(connector, source_key, run_id DESC);
                CREATE INDEX IF NOT EXISTS idx_ingest_runs_finished
                    ON ingest_runs(finished_at DESC);

                CREATE TABLE IF NOT EXISTS ingest_checkpoints (
                    connector TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    cursor_value TEXT,
                    source_watermark TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (connector, source_key)
                );
                """
            )

    def _is_empty(self) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM usage_event_heads LIMIT 1"
        ).fetchone()
        return row is None

    def _import_legacy_jsonl(self, path: Path) -> None:
        events: list[UsageEvent] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                try:
                    events.append(UsageEvent.from_dict(payload))
                except Exception:
                    continue
        if events:
            self.append_usage_events(events)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _event_record(self, event: UsageEvent) -> dict[str, Any]:
        payload = event.to_dict()
        payload.setdefault("metadata", {})
        return payload

    def _insert_revision(self, event: UsageEvent, revision: int) -> None:
        record = self._event_record(event)
        self._connection.execute(
            """
            INSERT INTO usage_events (
                event_id,
                revision,
                source_event_id,
                event_time,
                ingested_at,
                provider,
                model,
                model_family,
                project_id,
                attribution_confidence,
                attribution_reason_code,
                input_tokens_non_cached,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
                reasoning_tokens,
                source_type,
                source_path_or_key,
                lineage_hash,
                request_id,
                status,
                latency_ms,
                estimated_cost_usd,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["event_id"],
                revision,
                record["source_event_id"],
                record["event_time"],
                record["ingested_at"],
                record["provider"],
                record["model"],
                record["model_family"],
                record["project_id"],
                float(record["attribution_confidence"]),
                record["attribution_reason_code"],
                int(record["input_tokens_non_cached"]),
                int(record["output_tokens"]),
                int(record["cache_read_tokens"]),
                int(record["cache_write_tokens"]),
                record["reasoning_tokens"],
                record["source_type"],
                record["source_path_or_key"],
                record["lineage_hash"],
                record.get("request_id"),
                record.get("status"),
                record.get("latency_ms"),
                record.get("estimated_cost_usd"),
                json.dumps(record.get("metadata", {}), sort_keys=True),
            ),
        )
        self._connection.execute(
            """
            INSERT INTO usage_event_heads (event_id, revision, lineage_hash)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                revision = excluded.revision,
                lineage_hash = excluded.lineage_hash
            """,
            (event.event_id, revision, event.lineage_hash),
        )

    def append_usage_events(self, events: Iterable[UsageEvent]) -> int:
        inserted = 0
        with self._lock, self._connection:
            for event in events:
                head = self._connection.execute(
                    """
                    SELECT revision, lineage_hash
                    FROM usage_event_heads
                    WHERE event_id = ?
                    """,
                    (event.event_id,),
                ).fetchone()
                if head is not None and str(head["lineage_hash"]) == event.lineage_hash:
                    continue

                next_revision = 1 if head is None else int(head["revision"]) + 1
                self._insert_revision(event, next_revision)
                inserted += 1
        return inserted

    def all_events(self) -> list[UsageEvent]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT
                    e.event_id,
                    e.source_event_id,
                    e.event_time,
                    e.ingested_at,
                    e.provider,
                    e.model,
                    e.model_family,
                    e.project_id,
                    e.attribution_confidence,
                    e.attribution_reason_code,
                    e.input_tokens_non_cached,
                    e.output_tokens,
                    e.cache_read_tokens,
                    e.cache_write_tokens,
                    e.reasoning_tokens,
                    e.source_type,
                    e.source_path_or_key,
                    e.lineage_hash,
                    e.request_id,
                    e.status,
                    e.latency_ms,
                    e.estimated_cost_usd,
                    e.metadata_json,
                    h.revision AS event_revision
                FROM usage_events e
                JOIN usage_event_heads h
                    ON h.event_id = e.event_id
                   AND h.revision = e.revision
                ORDER BY e.event_time ASC, e.event_id ASC
                """
            ).fetchall()

        events: list[UsageEvent] = []
        for row in rows:
            payload = {
                "event_id": row["event_id"],
                "source_event_id": row["source_event_id"],
                "event_time": row["event_time"],
                "ingested_at": row["ingested_at"],
                "provider": row["provider"],
                "model": row["model"],
                "model_family": row["model_family"],
                "project_id": row["project_id"],
                "attribution_confidence": row["attribution_confidence"],
                "attribution_reason_code": row["attribution_reason_code"],
                "input_tokens_non_cached": row["input_tokens_non_cached"],
                "output_tokens": row["output_tokens"],
                "cache_read_tokens": row["cache_read_tokens"],
                "cache_write_tokens": row["cache_write_tokens"],
                "reasoning_tokens": row["reasoning_tokens"],
                "source_type": row["source_type"],
                "source_path_or_key": row["source_path_or_key"],
                "lineage_hash": row["lineage_hash"],
                "request_id": row["request_id"],
                "status": row["status"],
                "latency_ms": row["latency_ms"],
                "estimated_cost_usd": row["estimated_cost_usd"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
            events.append(UsageEvent.from_dict(payload))
        return events

    def record_ingest_run(
        self,
        *,
        connector: str,
        source_key: str,
        status: str,
        parsed_records: int = 0,
        inserted_records: int = 0,
        updated_records: int = 0,
        skipped_records: int = 0,
        malformed_records: int = 0,
        source_watermark: str | datetime | None = None,
        source_complete: bool = True,
        error_code: str | None = None,
        error_message: str | None = None,
        started_at: str | datetime | None = None,
        finished_at: str | datetime | None = None,
    ) -> int:
        if status not in {"success", "partial", "error"}:
            raise ValueError("status must be one of: success, partial, error")

        started = _coerce_datetime(started_at) or datetime.now(UTC)
        finished = _coerce_datetime(finished_at) or datetime.now(UTC)
        watermark = _coerce_datetime(source_watermark)

        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO ingest_runs (
                    connector,
                    source_key,
                    started_at,
                    finished_at,
                    status,
                    parsed_records,
                    inserted_records,
                    updated_records,
                    skipped_records,
                    malformed_records,
                    source_watermark,
                    source_complete,
                    error_code,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    connector.strip() or "unknown",
                    source_key.strip() or "default",
                    started.isoformat(),
                    finished.isoformat(),
                    status,
                    max(int(parsed_records), 0),
                    max(int(inserted_records), 0),
                    max(int(updated_records), 0),
                    max(int(skipped_records), 0),
                    max(int(malformed_records), 0),
                    watermark.isoformat() if watermark is not None else None,
                    1 if source_complete else 0,
                    error_code,
                    error_message,
                ),
            )
        return int(cursor.lastrowid or 0)

    def upsert_ingest_checkpoint(
        self,
        *,
        connector: str,
        source_key: str,
        cursor_value: str | None = None,
        source_watermark: str | datetime | None = None,
        updated_at: str | datetime | None = None,
    ) -> None:
        now = _coerce_datetime(updated_at) or datetime.now(UTC)
        watermark = _coerce_datetime(source_watermark)

        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO ingest_checkpoints (
                    connector,
                    source_key,
                    cursor_value,
                    source_watermark,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(connector, source_key) DO UPDATE SET
                    cursor_value = excluded.cursor_value,
                    source_watermark = excluded.source_watermark,
                    updated_at = excluded.updated_at
                """,
                (
                    connector.strip() or "unknown",
                    source_key.strip() or "default",
                    cursor_value,
                    watermark.isoformat() if watermark is not None else None,
                    now.isoformat(),
                ),
            )

    def ingest_status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest_runs = self._connection.execute(
                """
                SELECT r.*
                FROM ingest_runs r
                JOIN (
                    SELECT connector, source_key, MAX(run_id) AS latest_run_id
                    FROM ingest_runs
                    GROUP BY connector, source_key
                ) latest
                    ON latest.latest_run_id = r.run_id
                ORDER BY r.connector, r.source_key
                """
            ).fetchall()
            checkpoints = self._connection.execute(
                """
                SELECT connector, source_key, cursor_value, source_watermark, updated_at
                FROM ingest_checkpoints
                ORDER BY connector, source_key
                """
            ).fetchall()

        connectors: dict[str, dict[str, Any]] = {}
        for run in latest_runs:
            connector_name = str(run["connector"])
            connector = connectors.setdefault(
                connector_name,
                {
                    "connector": connector_name,
                    "latest_finished_at": None,
                    "latest_success_at": None,
                    "source_complete": True,
                    "source_watermark": None,
                    "sources": [],
                    "errors": [],
                },
            )

            finished_at = _coerce_datetime(run["finished_at"])
            success_finished_at = finished_at if run["status"] == "success" else None
            watermark = _coerce_datetime(run["source_watermark"])

            source_snapshot = {
                "source_key": run["source_key"],
                "status": run["status"],
                "started_at": run["started_at"],
                "finished_at": run["finished_at"],
                "parsed_records": int(run["parsed_records"] or 0),
                "inserted_records": int(run["inserted_records"] or 0),
                "updated_records": int(run["updated_records"] or 0),
                "skipped_records": int(run["skipped_records"] or 0),
                "malformed_records": int(run["malformed_records"] or 0),
                "source_complete": bool(run["source_complete"]),
                "source_watermark": watermark.isoformat() if watermark is not None else None,
                "error_code": run["error_code"],
                "error_message": run["error_message"],
            }
            connector["sources"].append(source_snapshot)

            if (
                finished_at is not None
                and (
                    connector["latest_finished_at"] is None
                    or finished_at > _coerce_datetime(connector["latest_finished_at"])
                )
            ):
                connector["latest_finished_at"] = finished_at.isoformat()

            if (
                success_finished_at is not None
                and (
                    connector["latest_success_at"] is None
                    or success_finished_at > _coerce_datetime(connector["latest_success_at"])
                )
            ):
                connector["latest_success_at"] = success_finished_at.isoformat()

            if run["status"] != "success" or not bool(run["source_complete"]):
                connector["source_complete"] = False
            if run["status"] != "success":
                connector["errors"].append(
                    {
                        "source_key": run["source_key"],
                        "status": run["status"],
                        "error_code": run["error_code"],
                        "error_message": run["error_message"],
                    }
                )

            if watermark is not None:
                current = _coerce_datetime(connector["source_watermark"])
                if current is None or watermark < current:
                    connector["source_watermark"] = watermark.isoformat()

        connector_snapshots = [connectors[key] for key in sorted(connectors)]
        global_watermark: datetime | None = None
        global_complete = True
        for connector in connector_snapshots:
            watermark = _coerce_datetime(connector.get("source_watermark"))
            if watermark is not None and (global_watermark is None or watermark < global_watermark):
                global_watermark = watermark
            if not bool(connector.get("source_complete", True)):
                global_complete = False

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_watermark": global_watermark.isoformat() if global_watermark else None,
            "source_complete": global_complete,
            "connectors": connector_snapshots,
            "checkpoints": [
                {
                    "connector": row["connector"],
                    "source_key": row["source_key"],
                    "cursor_value": row["cursor_value"],
                    "source_watermark": row["source_watermark"],
                    "updated_at": row["updated_at"],
                }
                for row in checkpoints
            ],
        }

    def _floor_bucket(self, dt: datetime, grain: str) -> datetime:
        normalized = dt.astimezone(UTC)
        if grain == "hour":
            return normalized.replace(minute=0, second=0, microsecond=0)
        if grain == "day":
            return normalized.replace(hour=0, minute=0, second=0, microsecond=0)
        raise ValueError(f"Unsupported grain: {grain}")

    def _aggregate(
        self,
        *,
        grain: str,
        provider: str | None = None,
        project_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[AggregateRow]:
        start = start_time.astimezone(UTC) if start_time else None
        end = end_time.astimezone(UTC) if end_time else None

        buckets: dict[tuple[datetime, str, str], dict[str, int]] = defaultdict(
            lambda: {
                "event_count": 0,
                "input_tokens_non_cached": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "tokens_total": 0,
            }
        )

        for event in self.all_events():
            if provider and event.provider != provider:
                continue
            if project_id and event.project_id != project_id:
                continue
            if start and event.event_time < start:
                continue
            if end and event.event_time >= end:
                continue

            bucket_time = self._floor_bucket(event.event_time, grain)
            key = (bucket_time, event.provider, event.project_id)
            current = buckets[key]
            current["event_count"] += 1
            current["input_tokens_non_cached"] += event.input_tokens_non_cached
            current["output_tokens"] += event.output_tokens
            current["cache_read_tokens"] += event.cache_read_tokens
            current["cache_write_tokens"] += event.cache_write_tokens
            current["reasoning_tokens"] += event.reasoning_tokens or 0
            current["tokens_total"] += event.tokens_total

        rows: list[AggregateRow] = []
        for (bucket_time, bucket_provider, bucket_project), totals in sorted(buckets.items()):
            rows.append(
                AggregateRow(
                    time_bucket=bucket_time,
                    provider=bucket_provider,
                    project_id=bucket_project,
                    event_count=totals["event_count"],
                    input_tokens_non_cached=totals["input_tokens_non_cached"],
                    output_tokens=totals["output_tokens"],
                    cache_read_tokens=totals["cache_read_tokens"],
                    cache_write_tokens=totals["cache_write_tokens"],
                    reasoning_tokens=totals["reasoning_tokens"],
                    tokens_total=totals["tokens_total"],
                )
            )
        return rows

    def aggregate_hourly(
        self,
        *,
        provider: str | None = None,
        project_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[AggregateRow]:
        return self._aggregate(
            grain="hour",
            provider=provider,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
        )

    def aggregate_daily(
        self,
        *,
        provider: str | None = None,
        project_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[AggregateRow]:
        return self._aggregate(
            grain="day",
            provider=provider,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
        )


def _default_backing_file() -> Path | None:
    raw = os.getenv("USAGE_EVENT_STORE_FILE", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _default_sqlite_path() -> str:
    explicit = os.getenv("USAGE_EVENT_STORE_DB", "").strip()
    if explicit:
        expanded = Path(explicit).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        return str(expanded)

    if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return ":memory:"

    root = Path("/tmp/ai-usage-observatory")
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "usage-events.sqlite3")


def _coerce_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


_DEFAULT_EVENT_STORE = UsageEventStore(
    sqlite_path=_default_sqlite_path(),
    backing_file=_default_backing_file(),
)


def append_usage_events(events: Iterable[UsageEvent]) -> int:
    """
    Compatibility adapter used by API route loaders.
    """
    return _DEFAULT_EVENT_STORE.append_usage_events(events)


def list_usage_events() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in _DEFAULT_EVENT_STORE.all_events():
        payload = event.to_dict()
        # Compatibility aliases consumed by cost-layer analytics.
        payload["cost_estimated_usd"] = payload.get("estimated_cost_usd")
        payload.setdefault("cost_billed_usd", None)
        rows.append(payload)
    return rows


def get_usage_events() -> list[dict[str, object]]:
    return list_usage_events()


def record_ingest_run(
    *,
    connector: str,
    source_key: str,
    status: str,
    parsed_records: int = 0,
    inserted_records: int = 0,
    updated_records: int = 0,
    skipped_records: int = 0,
    malformed_records: int = 0,
    source_watermark: str | datetime | None = None,
    source_complete: bool = True,
    error_code: str | None = None,
    error_message: str | None = None,
    started_at: str | datetime | None = None,
    finished_at: str | datetime | None = None,
) -> int:
    return _DEFAULT_EVENT_STORE.record_ingest_run(
        connector=connector,
        source_key=source_key,
        status=status,
        parsed_records=parsed_records,
        inserted_records=inserted_records,
        updated_records=updated_records,
        skipped_records=skipped_records,
        malformed_records=malformed_records,
        source_watermark=source_watermark,
        source_complete=source_complete,
        error_code=error_code,
        error_message=error_message,
        started_at=started_at,
        finished_at=finished_at,
    )


def upsert_ingest_checkpoint(
    *,
    connector: str,
    source_key: str,
    cursor_value: str | None = None,
    source_watermark: str | datetime | None = None,
    updated_at: str | datetime | None = None,
) -> None:
    _DEFAULT_EVENT_STORE.upsert_ingest_checkpoint(
        connector=connector,
        source_key=source_key,
        cursor_value=cursor_value,
        source_watermark=source_watermark,
        updated_at=updated_at,
    )


def get_ingest_status_snapshot() -> dict[str, Any]:
    return _DEFAULT_EVENT_STORE.ingest_status_snapshot()


def get_store_freshness_snapshot() -> dict[str, Any]:
    return get_ingest_status_snapshot()


def get_default_event_store() -> UsageEventStore:
    return _DEFAULT_EVENT_STORE


def reset_usage_event_store() -> None:
    global _DEFAULT_EVENT_STORE
    try:
        _DEFAULT_EVENT_STORE.close()
    except Exception:
        pass
    _DEFAULT_EVENT_STORE = UsageEventStore(
        sqlite_path=_default_sqlite_path(),
        backing_file=_default_backing_file(),
    )
