from __future__ import annotations

import copy
from typing import Any

CATALOG_VERSION = "2026-03-01"

_CERTIFIED_WIDGETS: tuple[dict[str, Any], ...] = (
    {
        "widget_id": "provider-token-split",
        "title": "Provider Token Split",
        "description": "Provider-level token split with freshness and attribution metadata.",
        "certification": "CERTIFIED",
        "metric_lineage": [
            "tokens_total",
            "tokens_input_non_cached",
            "tokens_output",
            "attribution_coverage_pct",
            "freshness_state",
        ],
        "analytics_route": "/metrics",
        "capability_tags": ["usage:read"],
        "deprecation": {"status": "active", "replaced_by": None},
        "parameter_schema": {
            "time_bucket": {
                "type": "enum",
                "values": ["hour", "day", "month"],
                "required": False,
                "default": "day",
            },
            "project_id": {
                "type": "string",
                "required": False,
            },
            "provider": {
                "type": "enum",
                "values": ["claude", "openai"],
                "required": False,
            },
        },
    },
    {
        "widget_id": "project-cost-variance",
        "title": "Project Cost Variance",
        "description": "Project-level estimated vs billed cost variance envelope.",
        "certification": "CERTIFIED",
        "metric_lineage": [
            "cost_estimated_usd",
            "cost_billed_usd",
            "cost_variance_usd",
            "project_cost_share_pct",
            "freshness_state",
        ],
        "analytics_route": "/projects",
        "capability_tags": ["usage:read", "finance:read"],
        "deprecation": {"status": "active", "replaced_by": None},
        "parameter_schema": {
            "time_bucket": {
                "type": "enum",
                "values": ["day", "month"],
                "required": False,
                "default": "day",
            },
            "project_id": {
                "type": "string",
                "required": False,
            },
            "include_unknown_project": {
                "type": "boolean",
                "required": False,
                "default": True,
            },
        },
    },
    {
        "widget_id": "memory-churn-overview",
        "title": "Memory Churn Overview",
        "description": "Metadata-only Claude memory churn trend by project.",
        "certification": "CERTIFIED",
        "metric_lineage": [
            "memory_total_bytes",
            "memory_updates_7d",
            "memory_bytes_delta_7d",
            "memory_staleness_days",
            "freshness_state",
        ],
        "analytics_route": "/memory/insights",
        "capability_tags": ["usage:read", "memory:read"],
        "deprecation": {"status": "active", "replaced_by": None},
        "parameter_schema": {
            "window": {
                "type": "enum",
                "values": ["day", "week"],
                "required": False,
                "default": "week",
            },
            "project_id": {
                "type": "string",
                "required": False,
            },
        },
    },
)



def list_certified_widgets() -> list[dict[str, Any]]:
    return [copy.deepcopy(widget) for widget in _CERTIFIED_WIDGETS]



def get_widget_definition(widget_id: str) -> dict[str, Any] | None:
    for widget in _CERTIFIED_WIDGETS:
        if widget["widget_id"] == widget_id:
            return copy.deepcopy(widget)
    return None



def get_certified_widget_ids() -> set[str]:
    return {widget["widget_id"] for widget in _CERTIFIED_WIDGETS}
