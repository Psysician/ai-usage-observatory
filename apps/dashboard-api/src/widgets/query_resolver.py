from __future__ import annotations

from typing import Any, Iterable, Mapping

from widgets.widget_catalog import CATALOG_VERSION, get_widget_definition

ROLE_CAPABILITIES: dict[str, set[str]] = {
    "Admin": {"usage:read", "finance:read", "memory:read", "views:write", "views:share"},
    "Editor": {"usage:read", "finance:read", "memory:read", "views:write"},
    "Analyst": {"usage:read", "finance:read", "memory:read"},
    "Viewer": {"usage:read"},
    "FinanceViewer": {"usage:read", "finance:read"},
}


class QueryResolutionError(ValueError):
    def __init__(self, *, code: str, message: str, path: str = "widget_query") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}



def _ensure_mapping(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise QueryResolutionError(code="invalid_type", path=path, message=f"Expected object at {path}.")
    return dict(value)



def _normalize_params(param_schema: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    params_obj = _ensure_mapping(params, path="widget_query.params")
    normalized: dict[str, Any] = {}

    unknown = sorted(set(params_obj.keys()) - set(param_schema.keys()))
    if unknown:
        raise QueryResolutionError(
            code="invalid_params",
            path="widget_query.params",
            message=f"Unexpected parameter(s): {', '.join(unknown)}.",
        )

    for name, rule_value in param_schema.items():
        rule = _ensure_mapping(rule_value, path=f"widget_query.param_schema.{name}")
        required = bool(rule.get("required", False))
        has_default = "default" in rule

        if name not in params_obj:
            if required and not has_default:
                raise QueryResolutionError(
                    code="invalid_params",
                    path=f"widget_query.params.{name}",
                    message=f"Missing required parameter {name!r}.",
                )
            if has_default:
                normalized[name] = rule["default"]
            continue

        value = params_obj[name]
        value_type = rule.get("type")

        if value_type == "string":
            if not isinstance(value, str) or not value.strip():
                raise QueryResolutionError(
                    code="invalid_params",
                    path=f"widget_query.params.{name}",
                    message=f"Parameter {name!r} must be a non-empty string.",
                )
            normalized[name] = value.strip()
            continue

        if value_type == "boolean":
            if not isinstance(value, bool):
                raise QueryResolutionError(
                    code="invalid_params",
                    path=f"widget_query.params.{name}",
                    message=f"Parameter {name!r} must be boolean.",
                )
            normalized[name] = value
            continue

        if value_type == "enum":
            allowed = rule.get("values", [])
            if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
                raise QueryResolutionError(
                    code="invalid_catalog",
                    path=f"widget_query.param_schema.{name}",
                    message=f"Catalog enum definition for {name!r} is invalid.",
                )
            if not isinstance(value, str) or value not in allowed:
                raise QueryResolutionError(
                    code="invalid_params",
                    path=f"widget_query.params.{name}",
                    message=f"Parameter {name!r} must be one of {allowed}.",
                )
            normalized[name] = value
            continue

        raise QueryResolutionError(
            code="invalid_catalog",
            path=f"widget_query.param_schema.{name}",
            message=f"Unsupported parameter type {value_type!r} in catalog.",
        )

    return normalized



def _resolve_capabilities(
    *,
    actor_role: str,
    actor_capabilities: Iterable[str] | None,
) -> set[str]:
    if actor_capabilities is not None:
        return {str(capability) for capability in actor_capabilities}

    if actor_role not in ROLE_CAPABILITIES:
        raise QueryResolutionError(
            code="invalid_role",
            path="widget_query.actor_role",
            message=f"Unsupported actor role {actor_role!r}.",
        )
    return set(ROLE_CAPABILITIES[actor_role])



def resolve_widget_query(
    widget_binding: Mapping[str, Any],
    *,
    actor_role: str,
    actor_capabilities: Iterable[str] | None = None,
) -> dict[str, Any]:
    binding = _ensure_mapping(widget_binding, path="widget_query.binding")

    required = {"binding_id", "widget_id", "params"}
    missing = sorted(required - set(binding.keys()))
    if missing:
        raise QueryResolutionError(
            code="missing_field",
            path="widget_query.binding",
            message=f"Missing binding field(s): {', '.join(missing)}.",
        )

    binding_id = binding.get("binding_id")
    widget_id = binding.get("widget_id")
    params = binding.get("params")

    if not isinstance(binding_id, str) or not binding_id.strip():
        raise QueryResolutionError(
            code="invalid_value",
            path="widget_query.binding.binding_id",
            message="binding_id must be a non-empty string.",
        )

    if not isinstance(widget_id, str) or not widget_id.strip():
        raise QueryResolutionError(
            code="invalid_value",
            path="widget_query.binding.widget_id",
            message="widget_id must be a non-empty string.",
        )

    widget = get_widget_definition(widget_id)
    if widget is None:
        raise QueryResolutionError(
            code="unknown_widget",
            path="widget_query.binding.widget_id",
            message=f"Unknown widget_id {widget_id!r}.",
        )

    resolved_capabilities = _resolve_capabilities(
        actor_role=actor_role,
        actor_capabilities=actor_capabilities,
    )

    required_capabilities = set(widget.get("capability_tags", []))
    missing_capabilities = sorted(required_capabilities - resolved_capabilities)
    if missing_capabilities:
        raise QueryResolutionError(
            code="permission_denied",
            path="widget_query.permissions",
            message=(
                f"Role {actor_role!r} lacks required capability tag(s): "
                f"{', '.join(missing_capabilities)}."
            ),
        )

    param_schema = _ensure_mapping(
        widget.get("parameter_schema", {}),
        path=f"widget_query.catalog.{widget_id}.parameter_schema",
    )
    normalized_params = _normalize_params(param_schema, params)

    return {
        "binding_id": binding_id,
        "widget_id": widget_id,
        "analytics_route": widget["analytics_route"],
        "params": normalized_params,
        "metric_lineage": list(widget["metric_lineage"]),
        "capability_tags": list(widget["capability_tags"]),
        "certification": widget["certification"],
        "provenance": {
            "catalog_version": CATALOG_VERSION,
            "widget_id": widget_id,
            "metric_lineage": list(widget["metric_lineage"]),
        },
    }



def resolve_view_queries(
    view_spec: Mapping[str, Any],
    *,
    actor_role: str,
    actor_capabilities: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    spec = _ensure_mapping(view_spec, path="view_spec")
    widgets = spec.get("widgets", [])
    if not isinstance(widgets, list):
        raise QueryResolutionError(
            code="invalid_type",
            path="view_spec.widgets",
            message="view_spec.widgets must be a list.",
        )

    return [
        resolve_widget_query(
            widget,
            actor_role=actor_role,
            actor_capabilities=actor_capabilities,
        )
        for widget in widgets
    ]
