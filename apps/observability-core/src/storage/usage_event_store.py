from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

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
    def __init__(self, *, backing_file: str | Path | None = None) -> None:
        self._events: list[UsageEvent] = []
        self._event_ids: set[str] = set()
        self._backing_file: Path | None = Path(backing_file) if backing_file else None

        if self._backing_file:
            self._backing_file.parent.mkdir(parents=True, exist_ok=True)
            if self._backing_file.exists():
                self._load_existing()

    def _load_existing(self) -> None:
        assert self._backing_file is not None
        with self._backing_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                event = UsageEvent.from_dict(payload)
                if event.event_id in self._event_ids:
                    continue
                self._event_ids.add(event.event_id)
                self._events.append(event)

    def append_usage_events(self, events: Iterable[UsageEvent]) -> int:
        inserted = 0
        batch: list[UsageEvent] = []
        for event in events:
            if event.event_id in self._event_ids:
                continue
            self._event_ids.add(event.event_id)
            self._events.append(event)
            batch.append(event)
            inserted += 1

        if self._backing_file and batch:
            with self._backing_file.open("a", encoding="utf-8") as handle:
                for event in batch:
                    handle.write(json.dumps(event.to_dict(), sort_keys=True))
                    handle.write("\n")

        return inserted

    def all_events(self) -> list[UsageEvent]:
        return list(self._events)

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

        for event in self._events:
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


_DEFAULT_EVENT_STORE = UsageEventStore()


def append_usage_events(events: Iterable[UsageEvent]) -> int:
    """
    Compatibility adapter used by API route loaders.
    """
    return _DEFAULT_EVENT_STORE.append_usage_events(events)


def list_usage_events() -> list[dict[str, object]]:
    return [event.to_dict() for event in _DEFAULT_EVENT_STORE.all_events()]


def get_usage_events() -> list[dict[str, object]]:
    return list_usage_events()


def reset_usage_event_store() -> None:
    global _DEFAULT_EVENT_STORE
    _DEFAULT_EVENT_STORE = UsageEventStore()
