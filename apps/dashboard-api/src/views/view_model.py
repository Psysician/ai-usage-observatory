from __future__ import annotations

import copy
import json
from typing import Any, Iterable, Mapping

VIEW_SCHEMA_VERSION = "1.0"
VALID_VIEW_SCOPES = {"personal", "team", "org"}
VALID_OWNER_ROLES = {"Admin", "Editor", "Analyst", "Viewer", "FinanceViewer"}
VALID_TIME_BUCKETS = {"hour", "day", "week", "month"}


class ViewValidationError(ValueError):
    def __init__(self, *, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}



def stable_json_dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)



def clone_view_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(spec))



def _ensure_mapping(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ViewValidationError(
            code="invalid_type",
            path=path,
            message=f"Expected object at {path}.",
        )
    return dict(value)



def _validate_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    path: str,
) -> None:
    key_set = set(value.keys())
    missing = sorted(required - key_set)
    unexpected = sorted(key_set - required - optional)

    if missing:
        raise ViewValidationError(
            code="missing_field",
            path=path,
            message=f"Missing required field(s): {', '.join(missing)}.",
        )

    if unexpected:
        raise ViewValidationError(
            code="unexpected_field",
            path=path,
            message=f"Unexpected field(s): {', '.join(unexpected)}.",
        )



def _ensure_string(
    value: Any,
    *,
    path: str,
    min_length: int = 1,
    max_length: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise ViewValidationError(
            code="invalid_type",
            path=path,
            message=f"Expected string at {path}.",
        )

    trimmed = value.strip()
    if len(trimmed) < min_length:
        raise ViewValidationError(
            code="invalid_value",
            path=path,
            message=f"Value at {path} must be at least {min_length} characters.",
        )

    if max_length is not None and len(trimmed) > max_length:
        raise ViewValidationError(
            code="invalid_value",
            path=path,
            message=f"Value at {path} must be at most {max_length} characters.",
        )

    return trimmed



def _ensure_int(
    value: Any,
    *,
    path: str,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ViewValidationError(
            code="invalid_type",
            path=path,
            message=f"Expected integer at {path}.",
        )

    if value < minimum:
        raise ViewValidationError(
            code="invalid_value",
            path=path,
            message=f"Value at {path} must be >= {minimum}.",
        )

    if maximum is not None and value > maximum:
        raise ViewValidationError(
            code="invalid_value",
            path=path,
            message=f"Value at {path} must be <= {maximum}.",
        )

    return value



def _normalize_layout(layout: Mapping[str, Any]) -> dict[str, Any]:
    layout_obj = _ensure_mapping(layout, path="view_spec.layout")
    _validate_keys(
        layout_obj,
        required={"columns", "items"},
        optional={"row_height"},
        path="view_spec.layout",
    )

    columns = _ensure_int(layout_obj["columns"], path="view_spec.layout.columns", minimum=1, maximum=24)
    row_height = _ensure_int(
        layout_obj.get("row_height", 32),
        path="view_spec.layout.row_height",
        minimum=1,
        maximum=400,
    )

    raw_items = layout_obj["items"]
    if not isinstance(raw_items, list) or not raw_items:
        raise ViewValidationError(
            code="invalid_value",
            path="view_spec.layout.items",
            message="view_spec.layout.items must be a non-empty list.",
        )

    normalized_items: list[dict[str, Any]] = []
    binding_ids: set[str] = set()

    for index, item in enumerate(raw_items):
        item_path = f"view_spec.layout.items[{index}]"
        item_obj = _ensure_mapping(item, path=item_path)
        _validate_keys(
            item_obj,
            required={"binding_id", "x", "y", "w", "h"},
            optional=set(),
            path=item_path,
        )

        binding_id = _ensure_string(
            item_obj["binding_id"],
            path=f"{item_path}.binding_id",
            min_length=1,
            max_length=80,
        )
        if binding_id in binding_ids:
            raise ViewValidationError(
                code="duplicate_binding",
                path=f"{item_path}.binding_id",
                message=f"Duplicate binding_id {binding_id!r}.",
            )

        x = _ensure_int(item_obj["x"], path=f"{item_path}.x", minimum=0)
        y = _ensure_int(item_obj["y"], path=f"{item_path}.y", minimum=0)
        w = _ensure_int(item_obj["w"], path=f"{item_path}.w", minimum=1, maximum=columns)
        h = _ensure_int(item_obj["h"], path=f"{item_path}.h", minimum=1, maximum=200)

        if x + w > columns:
            raise ViewValidationError(
                code="invalid_layout",
                path=item_path,
                message=(
                    "Layout item exceeds grid bounds: "
                    f"x({x}) + w({w}) must be <= columns({columns})."
                ),
            )

        binding_ids.add(binding_id)
        normalized_items.append({"binding_id": binding_id, "x": x, "y": y, "w": w, "h": h})

    return {
        "columns": columns,
        "row_height": row_height,
        "items": normalized_items,
    }



def _normalize_filters(filters: Mapping[str, Any]) -> dict[str, Any]:
    filters_obj = _ensure_mapping(filters, path="view_spec.filters")
    _validate_keys(
        filters_obj,
        required=set(),
        optional={"time_bucket", "project_id", "provider", "model", "model_family"},
        path="view_spec.filters",
    )

    normalized: dict[str, Any] = {}

    time_bucket = filters_obj.get("time_bucket", "day")
    if not isinstance(time_bucket, str):
        raise ViewValidationError(
            code="invalid_type",
            path="view_spec.filters.time_bucket",
            message="time_bucket must be a string.",
        )
    if time_bucket not in VALID_TIME_BUCKETS:
        raise ViewValidationError(
            code="invalid_value",
            path="view_spec.filters.time_bucket",
            message=(
                "time_bucket must be one of "
                f"{sorted(VALID_TIME_BUCKETS)}."
            ),
        )
    normalized["time_bucket"] = time_bucket

    for key in ("project_id", "provider", "model", "model_family"):
        value = filters_obj.get(key)
        if value is None:
            continue
        normalized[key] = _ensure_string(
            value,
            path=f"view_spec.filters.{key}",
            min_length=1,
            max_length=120,
        )

    if "provider" in normalized and normalized["provider"] not in {"claude", "openai"}:
        raise ViewValidationError(
            code="invalid_value",
            path="view_spec.filters.provider",
            message="provider must be 'claude' or 'openai'.",
        )

    return normalized



def _normalize_widgets(
    widgets: Any,
    *,
    scope: str,
    certified_widget_ids: set[str] | None,
) -> list[dict[str, Any]]:
    if not isinstance(widgets, list) or not widgets:
        raise ViewValidationError(
            code="invalid_value",
            path="view_spec.widgets",
            message="view_spec.widgets must be a non-empty list.",
        )

    if len(widgets) > 64:
        raise ViewValidationError(
            code="invalid_value",
            path="view_spec.widgets",
            message="view_spec.widgets supports up to 64 entries.",
        )

    normalized: list[dict[str, Any]] = []
    binding_ids: set[str] = set()

    for index, widget in enumerate(widgets):
        widget_path = f"view_spec.widgets[{index}]"
        widget_obj = _ensure_mapping(widget, path=widget_path)
        _validate_keys(
            widget_obj,
            required={"binding_id", "widget_id", "params"},
            optional={"title", "overrides"},
            path=widget_path,
        )

        binding_id = _ensure_string(
            widget_obj["binding_id"],
            path=f"{widget_path}.binding_id",
            min_length=1,
            max_length=80,
        )
        widget_id = _ensure_string(
            widget_obj["widget_id"],
            path=f"{widget_path}.widget_id",
            min_length=1,
            max_length=120,
        )

        if binding_id in binding_ids:
            raise ViewValidationError(
                code="duplicate_binding",
                path=f"{widget_path}.binding_id",
                message=f"Duplicate binding_id {binding_id!r}.",
            )

        params = _ensure_mapping(widget_obj["params"], path=f"{widget_path}.params")
        overrides = _ensure_mapping(widget_obj.get("overrides", {}), path=f"{widget_path}.overrides")

        title_value = widget_obj.get("title")
        title = None
        if title_value is not None:
            title = _ensure_string(
                title_value,
                path=f"{widget_path}.title",
                min_length=1,
                max_length=120,
            )

        if scope in {"team", "org"} and certified_widget_ids is not None:
            if widget_id not in certified_widget_ids:
                raise ViewValidationError(
                    code="non_certified_widget",
                    path=f"{widget_path}.widget_id",
                    message=(
                        f"Widget {widget_id!r} is not certified and cannot be used "
                        f"for {scope} scope views."
                    ),
                )

        item: dict[str, Any] = {
            "binding_id": binding_id,
            "widget_id": widget_id,
            "params": params,
            "overrides": overrides,
        }
        if title is not None:
            item["title"] = title

        binding_ids.add(binding_id)
        normalized.append(item)

    return normalized



def _validate_bindings(
    *,
    layout_binding_ids: Iterable[str],
    widget_binding_ids: Iterable[str],
) -> None:
    layout_set = set(layout_binding_ids)
    widget_set = set(widget_binding_ids)

    only_in_layout = sorted(layout_set - widget_set)
    only_in_widgets = sorted(widget_set - layout_set)

    if only_in_layout or only_in_widgets:
        parts: list[str] = []
        if only_in_layout:
            parts.append(f"layout-only={only_in_layout}")
        if only_in_widgets:
            parts.append(f"widgets-only={only_in_widgets}")
        raise ViewValidationError(
            code="layout_binding_mismatch",
            path="view_spec",
            message="Layout/widget binding mismatch: " + "; ".join(parts) + ".",
        )



def validate_view_spec(
    view_spec: Mapping[str, Any],
    *,
    certified_widget_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    spec = _ensure_mapping(view_spec, path="view_spec")
    _validate_keys(
        spec,
        required={"schema_version", "name", "scope", "owner", "layout", "filters", "widgets"},
        optional=set(),
        path="view_spec",
    )

    schema_version = _ensure_string(
        spec["schema_version"],
        path="view_spec.schema_version",
        min_length=1,
        max_length=24,
    )
    if schema_version != VIEW_SCHEMA_VERSION:
        raise ViewValidationError(
            code="unsupported_schema_version",
            path="view_spec.schema_version",
            message=f"Unsupported schema_version {schema_version!r}.",
        )

    name = _ensure_string(spec["name"], path="view_spec.name", min_length=1, max_length=120)

    scope = _ensure_string(spec["scope"], path="view_spec.scope", min_length=1, max_length=32)
    if scope not in VALID_VIEW_SCOPES:
        raise ViewValidationError(
            code="invalid_value",
            path="view_spec.scope",
            message=f"scope must be one of {sorted(VALID_VIEW_SCOPES)}.",
        )

    owner_obj = _ensure_mapping(spec["owner"], path="view_spec.owner")
    _validate_keys(
        owner_obj,
        required={"user_id", "role"},
        optional=set(),
        path="view_spec.owner",
    )
    owner_user_id = _ensure_string(
        owner_obj["user_id"],
        path="view_spec.owner.user_id",
        min_length=1,
        max_length=120,
    )
    owner_role = _ensure_string(
        owner_obj["role"],
        path="view_spec.owner.role",
        min_length=1,
        max_length=64,
    )
    if owner_role not in VALID_OWNER_ROLES:
        raise ViewValidationError(
            code="invalid_value",
            path="view_spec.owner.role",
            message=f"owner.role must be one of {sorted(VALID_OWNER_ROLES)}.",
        )

    layout = _normalize_layout(spec["layout"])
    filters = _normalize_filters(spec["filters"])
    widget_ids = set(certified_widget_ids or [])
    widgets = _normalize_widgets(
        spec["widgets"],
        scope=scope,
        certified_widget_ids=widget_ids if widget_ids else None,
    )

    _validate_bindings(
        layout_binding_ids=[item["binding_id"] for item in layout["items"]],
        widget_binding_ids=[item["binding_id"] for item in widgets],
    )

    return {
        "schema_version": schema_version,
        "name": name,
        "scope": scope,
        "owner": {"user_id": owner_user_id, "role": owner_role},
        "layout": layout,
        "filters": filters,
        "widgets": widgets,
    }
