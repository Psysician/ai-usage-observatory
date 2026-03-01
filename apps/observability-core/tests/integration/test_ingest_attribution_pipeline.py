from __future__ import annotations

import json

from ingest.attribution.project_attribution import resolve_project_attribution
from ingest.providers.claude_local import adapt_claude_local_records
from ingest.providers.codex_lb_request_logs import adapt_codex_lb_request_logs
from ingest.providers.openai_codex_local import adapt_openai_codex_local_records
from storage.usage_event_store import UsageEventStore


def _fixture_records() -> tuple[list[str], list[str], list[str]]:
    claude_records = [
        json.dumps(
            {
                "id": "claude-evt-1",
                "timestamp": "2026-02-28T10:15:00Z",
                "model": "claude-3-7-sonnet",
                "project_id": "project-alpha",
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 30,
                    "cache_read_input_tokens": 50,
                    "cache_creation_input_tokens": 20,
                },
            }
        ),
        "{malformed json",
        json.dumps(
            {
                "id": "claude-evt-2",
                "timestamp": "2026-02-28T10:45:00Z",
                "model": "claude-3-5-haiku",
                "session_id": "sess-claude-2",
                "cwd": "/home/franky/repos/project-beta",
                "usage": {
                    "input_tokens": 60,
                    "output_tokens": 10,
                },
            }
        ),
    ]

    openai_records = [
        json.dumps(
            {
                "id": "openai-evt-1",
                "created": "2026-02-28T11:05:00Z",
                "model": "gpt-4.1",
                "session": {"id": "sess-openai-1", "cwd": "/home/franky/repos/project-gamma"},
                "usage": {
                    "prompt_tokens": 90,
                    "completion_tokens": 45,
                    "cached_tokens": 15,
                    "reasoning_tokens": 20,
                },
            }
        ),
        json.dumps(
            {
                "id": "openai-evt-2",
                "created": "2026-02-28T11:20:00Z",
                "model": "gpt-4.1-mini",
                "cwd": "/tmp/workspaces/project-theta/src",
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 5,
                },
            }
        ),
    ]

    codex_lb_records = [
        json.dumps(
            {
                "request_id": "lb-evt-1",
                "timestamp": "2026-02-28T12:00:00Z",
                "model": "gpt-4.1",
                "provider": "openai",
                "cwd": "/home/franky/repos/project-delta",
                "prompt_tokens": 200,
                "completion_tokens": 80,
                "cached_prompt_tokens": 30,
                "status": 200,
                "latency_ms": 900,
            }
        ),
        json.dumps(
            {
                "request_id": "lb-evt-2",
                "timestamp": "2026-02-28T12:25:00Z",
                "model": "gpt-4.1",
                "prompt_tokens": 50,
                "completion_tokens": 25,
                "cached_prompt_tokens": 5,
                "reasoning_tokens": 3,
            }
        ),
        "not-json",
    ]

    return claude_records, openai_records, codex_lb_records


def test_ingest_attribution_pipeline_aggregates_match_source_totals() -> None:
    claude_records, openai_records, codex_lb_records = _fixture_records()

    session_project_map = {
        "sess-claude-2": "project-beta",
        "sess-openai-1": "project-gamma",
    }
    workspace_project_map = {
        "/home/franky/repos/project-delta": "project-delta",
    }

    claude_events, claude_stats = adapt_claude_local_records(
        claude_records,
        source_path="fixtures/claude_local.jsonl",
        session_project_map=session_project_map,
        workspace_project_map=workspace_project_map,
    )
    openai_events, openai_stats = adapt_openai_codex_local_records(
        openai_records,
        source_path="fixtures/openai_codex_local.jsonl",
        session_project_map=session_project_map,
        workspace_project_map=workspace_project_map,
    )
    codex_lb_events, codex_lb_stats = adapt_codex_lb_request_logs(
        codex_lb_records,
        source_path="fixtures/codex_lb_request_logs.jsonl",
        session_project_map=session_project_map,
        workspace_project_map=workspace_project_map,
    )

    assert claude_stats.skipped_malformed_lines == 1
    assert openai_stats.skipped_malformed_lines == 0
    assert codex_lb_stats.skipped_malformed_lines == 1

    all_events = claude_events + openai_events + codex_lb_events
    assert len(all_events) == 6

    store = UsageEventStore()
    inserted = store.append_usage_events(all_events)
    replay_inserted = store.append_usage_events(all_events)
    assert inserted == 6
    assert replay_inserted == 0

    expected_totals = {
        "input_tokens_non_cached": 550,
        "output_tokens": 195,
        "cache_read_tokens": 100,
        "cache_write_tokens": 20,
        "reasoning_tokens": 23,
        "tokens_total": 888,
    }

    for aggregate_rows in (store.aggregate_hourly(), store.aggregate_daily()):
        observed_totals = {
            "input_tokens_non_cached": sum(r.input_tokens_non_cached for r in aggregate_rows),
            "output_tokens": sum(r.output_tokens for r in aggregate_rows),
            "cache_read_tokens": sum(r.cache_read_tokens for r in aggregate_rows),
            "cache_write_tokens": sum(r.cache_write_tokens for r in aggregate_rows),
            "reasoning_tokens": sum(r.reasoning_tokens for r in aggregate_rows),
            "tokens_total": sum(r.tokens_total for r in aggregate_rows),
        }
        for field, expected in expected_totals.items():
            observed = observed_totals[field]
            assert abs(observed - expected) <= 0


def test_every_event_has_provider_and_project_with_confidence_and_reason_code() -> None:
    claude_records, openai_records, codex_lb_records = _fixture_records()
    claude_events, _ = adapt_claude_local_records(
        claude_records,
        source_path="fixtures/claude_local.jsonl",
    )
    openai_events, _ = adapt_openai_codex_local_records(
        openai_records,
        source_path="fixtures/openai_codex_local.jsonl",
    )
    codex_lb_events, _ = adapt_codex_lb_request_logs(
        codex_lb_records,
        source_path="fixtures/codex_lb_request_logs.jsonl",
    )

    store = UsageEventStore()
    store.append_usage_events(claude_events + openai_events + codex_lb_events)
    events = store.all_events()
    assert events

    unknown_seen = False
    for event in events:
        assert event.provider in {"claude", "openai"}
        assert event.project_id
        assert 0.0 <= event.attribution_confidence <= 1.0
        assert event.attribution_reason_code
        if event.project_id == "unknown":
            unknown_seen = True
            assert event.attribution_confidence == 0.0
            assert event.attribution_reason_code == "unknown_fallback"

    assert unknown_seen


def test_attribution_ladder_is_deterministic() -> None:
    kwargs = {
        "explicit_project_id": None,
        "session_id": "sess-42",
        "source_path": "/var/logs/usage.jsonl",
        "workspace_path": "/home/franky/repos/project-zeta",
        "metadata": {"team": "core"},
        "session_project_map": {"sess-42": "project-omega"},
        "workspace_project_map": {"/home/franky/repos/project-zeta": "project-zeta"},
    }

    first = resolve_project_attribution(**kwargs)
    for _ in range(50):
        current = resolve_project_attribution(**kwargs)
        assert current == first

