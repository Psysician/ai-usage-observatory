from __future__ import annotations

from datetime import datetime, timezone

from ingest.normalization.usage_event import normalize_usage_event
from storage.usage_event_store import UsageEventStore


def _event(*, output_tokens: int) -> object:
    return normalize_usage_event(
        provider="claude",
        source_type="fixture",
        source_path_or_key="tests://usage-event-store",
        source_event_id="evt-1",
        event_time=datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc),
        model="claude-3-7-sonnet",
        project_id="project-alpha",
        attribution_confidence=0.95,
        attribution_reason_code="explicit_project_marker",
        input_tokens_non_cached=120,
        output_tokens=output_tokens,
        cache_read_tokens=5,
        cache_write_tokens=2,
        estimated_cost_usd=0.33,
    )


def test_store_tracks_revisions_when_lineage_changes() -> None:
    store = UsageEventStore(sqlite_path=":memory:")
    first = _event(output_tokens=40)
    replay = _event(output_tokens=40)
    corrected = _event(output_tokens=60)

    inserted_first = store.append_usage_events([first])
    inserted_replay = store.append_usage_events([replay])
    inserted_corrected = store.append_usage_events([corrected])

    assert inserted_first == 1
    assert inserted_replay == 0
    assert inserted_corrected == 1

    latest = store.all_events()
    assert len(latest) == 1
    assert latest[0].output_tokens == 60
    assert latest[0].tokens_total == 187


def test_ingest_status_snapshot_surfaces_watermark_completeness_and_checkpoints() -> None:
    store = UsageEventStore(sqlite_path=":memory:")
    run_one = store.record_ingest_run(
        connector="claude_local",
        source_key="tests://claude.jsonl",
        status="success",
        parsed_records=5,
        inserted_records=5,
        source_watermark=datetime(2026, 3, 1, 8, 30, tzinfo=timezone.utc),
        source_complete=True,
    )
    run_two = store.record_ingest_run(
        connector="openai_codex_local",
        source_key="tests://codex.jsonl",
        status="partial",
        parsed_records=4,
        inserted_records=3,
        malformed_records=1,
        source_watermark=datetime(2026, 3, 1, 8, 45, tzinfo=timezone.utc),
        source_complete=False,
        error_code="source_snapshot_incomplete",
        error_message="One record was malformed.",
    )
    assert run_one > 0
    assert run_two > run_one

    store.upsert_ingest_checkpoint(
        connector="claude_local",
        source_key="tests://claude.jsonl",
        cursor_value="offset:5",
        source_watermark=datetime(2026, 3, 1, 8, 30, tzinfo=timezone.utc),
    )

    snapshot = store.ingest_status_snapshot()
    assert snapshot["source_watermark"] is not None
    assert snapshot["source_complete"] is False
    assert len(snapshot["connectors"]) == 2
    assert len(snapshot["checkpoints"]) == 1

    claude = next(item for item in snapshot["connectors"] if item["connector"] == "claude_local")
    codex = next(
        item for item in snapshot["connectors"] if item["connector"] == "openai_codex_local"
    )
    assert claude["source_complete"] is True
    assert codex["source_complete"] is False
    assert codex["errors"]
