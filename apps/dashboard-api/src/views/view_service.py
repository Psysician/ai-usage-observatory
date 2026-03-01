from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from views.view_model import VIEW_SCHEMA_VERSION, stable_json_dumps, validate_view_spec


class ViewNotFoundError(KeyError):
    def __init__(self, view_id: str) -> None:
        super().__init__(f"View {view_id!r} was not found.")
        self.view_id = view_id


class InMemoryViewService:
    def __init__(
        self,
        *,
        certified_widget_ids: Iterable[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._certified_widget_ids = set(certified_widget_ids or [])
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._views: dict[str, dict[str, Any]] = {}

    def _timestamp(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    def _new_view_id(self) -> str:
        while True:
            candidate = f"view-{uuid4().hex[:12]}"
            if candidate not in self._views:
                return candidate

    def create_view(
        self,
        view_spec: Mapping[str, Any],
        *,
        view_id: str | None = None,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_spec = validate_view_spec(
            view_spec,
            certified_widget_ids=self._certified_widget_ids,
        )

        record_id = view_id or self._new_view_id()
        if record_id in self._views:
            raise ValueError(f"View {record_id!r} already exists.")

        now = self._timestamp()
        actor = actor_user_id or normalized_spec["owner"]["user_id"]
        record = {
            "view_id": record_id,
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
            "spec": normalized_spec,
        }

        if normalized_spec["scope"] in {"team", "org"}:
            record["share_key"] = f"{normalized_spec['scope']}:{record_id}"

        self._views[record_id] = record
        return copy.deepcopy(record)

    def get_view(self, view_id: str) -> dict[str, Any]:
        if view_id not in self._views:
            raise ViewNotFoundError(view_id)
        return copy.deepcopy(self._views[view_id])

    def update_view(
        self,
        view_id: str,
        view_spec: Mapping[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self._views.get(view_id)
        if existing is None:
            raise ViewNotFoundError(view_id)

        normalized_spec = validate_view_spec(
            view_spec,
            certified_widget_ids=self._certified_widget_ids,
        )

        actor = actor_user_id or normalized_spec["owner"]["user_id"]
        updated = {
            "view_id": view_id,
            "version": int(existing["version"]) + 1,
            "created_at": existing["created_at"],
            "updated_at": self._timestamp(),
            "created_by": existing["created_by"],
            "updated_by": actor,
            "spec": normalized_spec,
        }

        if normalized_spec["scope"] in {"team", "org"}:
            updated["share_key"] = f"{normalized_spec['scope']}:{view_id}"

        cloned_from = existing.get("cloned_from_view_id")
        if cloned_from is not None:
            updated["cloned_from_view_id"] = cloned_from

        self._views[view_id] = updated
        return copy.deepcopy(updated)

    def clone_view(
        self,
        source_view_id: str,
        *,
        name: str | None = None,
        owner: Mapping[str, Any] | None = None,
        scope: str | None = None,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        source = self.get_view(source_view_id)
        spec = copy.deepcopy(source["spec"])

        if name is not None:
            spec["name"] = name
        if owner is not None:
            spec["owner"] = dict(owner)
        if scope is not None:
            spec["scope"] = scope

        cloned = self.create_view(spec, actor_user_id=actor_user_id)
        self._views[cloned["view_id"]]["cloned_from_view_id"] = source_view_id
        cloned["cloned_from_view_id"] = source_view_id
        return cloned

    def delete_view(self, view_id: str) -> None:
        if view_id not in self._views:
            raise ViewNotFoundError(view_id)
        del self._views[view_id]

    def list_views(
        self,
        *,
        scope: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        views = [copy.deepcopy(record) for record in self._views.values()]
        if scope is not None:
            views = [record for record in views if record["spec"]["scope"] == scope]
        if owner_user_id is not None:
            views = [
                record
                for record in views
                if record["spec"]["owner"]["user_id"] == owner_user_id
            ]

        views.sort(key=lambda record: (record["created_at"], record["view_id"]))
        return views

    def export_snapshot(self) -> str:
        payload = {
            "schema_version": VIEW_SCHEMA_VERSION,
            "views": self.list_views(),
        }
        return stable_json_dumps(payload)

    def export_shared_snapshot(self) -> str:
        shared_views = [
            record
            for record in self.list_views()
            if record["spec"]["scope"] in {"team", "org"}
        ]
        payload = {
            "schema_version": VIEW_SCHEMA_VERSION,
            "shared_views": shared_views,
        }
        return stable_json_dumps(payload)

    def load_snapshot(self, snapshot: str | Mapping[str, Any]) -> None:
        parsed: Any
        if isinstance(snapshot, str):
            parsed = json.loads(snapshot)
        else:
            parsed = dict(snapshot)

        if not isinstance(parsed, Mapping):
            raise ValueError("Snapshot must be an object.")

        schema_version = parsed.get("schema_version")
        if schema_version != VIEW_SCHEMA_VERSION:
            raise ValueError(f"Unsupported snapshot schema_version {schema_version!r}.")

        views_raw = parsed.get("views")
        if not isinstance(views_raw, list):
            raise ValueError("Snapshot must include 'views' list.")

        restored: dict[str, dict[str, Any]] = {}
        for index, raw_record in enumerate(views_raw):
            if not isinstance(raw_record, Mapping):
                raise ValueError(f"Snapshot view at index {index} must be an object.")

            record = dict(raw_record)
            required_fields = {
                "view_id",
                "version",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "spec",
            }
            missing = sorted(required_fields - set(record.keys()))
            if missing:
                raise ValueError(
                    "Snapshot view at index "
                    f"{index} is missing required field(s): {', '.join(missing)}."
                )

            view_id = record["view_id"]
            if not isinstance(view_id, str) or not view_id.strip():
                raise ValueError(f"Snapshot view at index {index} has invalid view_id.")
            if view_id in restored:
                raise ValueError(f"Duplicate view_id {view_id!r} in snapshot.")

            version = record["version"]
            if not isinstance(version, int) or version < 1:
                raise ValueError(f"Snapshot view {view_id!r} has invalid version.")

            spec = validate_view_spec(
                record["spec"],
                certified_widget_ids=self._certified_widget_ids,
            )

            normalized_record: dict[str, Any] = {
                "view_id": view_id,
                "version": version,
                "created_at": str(record["created_at"]),
                "updated_at": str(record["updated_at"]),
                "created_by": str(record["created_by"]),
                "updated_by": str(record["updated_by"]),
                "spec": spec,
            }

            cloned_from = record.get("cloned_from_view_id")
            if cloned_from is not None:
                normalized_record["cloned_from_view_id"] = str(cloned_from)

            share_key = record.get("share_key")
            if share_key is not None:
                normalized_record["share_key"] = str(share_key)
            elif spec["scope"] in {"team", "org"}:
                normalized_record["share_key"] = f"{spec['scope']}:{view_id}"

            restored[view_id] = normalized_record

        self._views = restored

    @classmethod
    def from_snapshot(
        cls,
        snapshot: str | Mapping[str, Any],
        *,
        certified_widget_ids: Iterable[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> "InMemoryViewService":
        service = cls(certified_widget_ids=certified_widget_ids, clock=clock)
        service.load_snapshot(snapshot)
        return service
