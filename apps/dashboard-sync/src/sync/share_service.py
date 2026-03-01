from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sync.redaction_policy import RedactionResult, redact_view_payload

SHARE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class TeamShareExport:
    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)



class TeamShareService:
    """Build redacted team-share payloads from local dashboard views."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _timestamp(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def export_view(
        self,
        view_record: Mapping[str, Any],
        *,
        allowlist: Iterable[str] | None = None,
        shared_by: str | None = None,
    ) -> TeamShareExport:
        scope = str(view_record.get("spec", {}).get("scope", "personal"))
        if scope not in {"team", "org"}:
            raise ValueError(
                "Team sync export requires scope to be 'team' or 'org'. "
                f"Received {scope!r}."
            )

        redaction: RedactionResult = redact_view_payload(view_record, allowlist=allowlist)

        export = {
            "schema_version": SHARE_SCHEMA_VERSION,
            "exported_at": self._timestamp(),
            "scope": scope,
            "shared_by": shared_by,
            "view": redaction.payload,
            "redaction": {
                "policy": "strict-allowlist-v1",
                "redacted_paths": list(redaction.redacted_paths),
                "allowlisted_sensitive_paths": list(redaction.allowlisted_sensitive_paths),
            },
        }
        return TeamShareExport(payload=export)



def build_team_share_export(
    view_record: Mapping[str, Any],
    *,
    allowlist: Iterable[str] | None = None,
    shared_by: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    service = TeamShareService(clock=clock)
    return service.export_view(
        view_record,
        allowlist=allowlist,
        shared_by=shared_by,
    ).payload
