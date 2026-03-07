from __future__ import annotations

import sqlite3
from pathlib import Path

from ingest.local_ingest_runner import IngestSource, run_ingest_cycle
from storage.usage_event_store import UsageEventStore


def _create_codex_lb_sqlite(path: Path) -> None:
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE request_logs (
                id INTEGER PRIMARY KEY,
                account_id TEXT NOT NULL,
                api_key_id TEXT,
                request_id TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cached_input_tokens INTEGER,
                reasoning_tokens INTEGER,
                reasoning_effort TEXT,
                latency_ms INTEGER,
                status TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def _insert_row(
    path: Path,
    *,
    row_id: int,
    request_id: str,
    requested_at: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    reasoning_tokens: int | None = None,
    latency_ms: int = 0,
    status: str = "success",
) -> None:
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            """
            INSERT INTO request_logs (
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                "acct-1",
                None,
                request_id,
                requested_at,
                model,
                input_tokens,
                output_tokens,
                cached_input_tokens,
                reasoning_tokens,
                None,
                latency_ms,
                status,
                None,
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _checkpoint_for(store: UsageEventStore, connector: str, source_key: str) -> dict[str, str]:
    snapshot = store.ingest_status_snapshot()
    checkpoints = snapshot.get("checkpoints", [])
    assert isinstance(checkpoints, list)
    checkpoint = next(
        item
        for item in checkpoints
        if item.get("connector") == connector and item.get("source_key") == source_key
    )
    assert isinstance(checkpoint, dict)
    return checkpoint


def test_codex_lb_sqlite_ingest_backfills_then_increments(tmp_path: Path) -> None:
    db_path = tmp_path / "codex-lb-store.db"
    _create_codex_lb_sqlite(db_path)
    _insert_row(
        db_path,
        row_id=1,
        request_id="req-1",
        requested_at="2026-03-01 20:12:07.461383",
        model="gpt-5.3-codex",
        input_tokens=100,
        output_tokens=25,
        cached_input_tokens=10,
        reasoning_tokens=5,
        latency_ms=1000,
    )
    _insert_row(
        db_path,
        row_id=2,
        request_id="req-2",
        requested_at="2026-03-01 20:12:17.626327",
        model="gpt-5.3-codex",
        input_tokens=80,
        output_tokens=20,
        cached_input_tokens=8,
        reasoning_tokens=4,
        latency_ms=900,
    )

    store = UsageEventStore(sqlite_path=":memory:")
    source = IngestSource(connector="codex_lb_sqlite", source_path=db_path)

    first = run_ingest_cycle(store=store, sources=[source])
    assert first["source_count"] == 1
    assert first["parsed_records"] == 2
    assert first["inserted_records"] == 2
    assert first["malformed_records"] == 0
    assert len(store.all_events()) == 2
    checkpoint = _checkpoint_for(store, "codex_lb_sqlite", str(db_path))
    assert checkpoint["cursor_value"] == "id:2"

    _insert_row(
        db_path,
        row_id=3,
        request_id="req-3",
        requested_at="2026-03-01 20:12:27.192122",
        model="gpt-5.3-codex",
        input_tokens=70,
        output_tokens=10,
        cached_input_tokens=7,
        reasoning_tokens=3,
        latency_ms=800,
    )

    second = run_ingest_cycle(store=store, sources=[source])
    assert second["source_count"] == 1
    assert second["parsed_records"] == 1
    assert second["inserted_records"] == 1
    assert second["malformed_records"] == 0
    assert len(store.all_events()) == 3
    checkpoint = _checkpoint_for(store, "codex_lb_sqlite", str(db_path))
    assert checkpoint["cursor_value"] == "id:3"

    third = run_ingest_cycle(store=store, sources=[source])
    assert third["source_count"] == 1
    assert third["parsed_records"] == 0
    assert third["inserted_records"] == 0
    assert third["malformed_records"] == 0
    checkpoint = _checkpoint_for(store, "codex_lb_sqlite", str(db_path))
    assert checkpoint["cursor_value"] == "id:3"
