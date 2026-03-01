from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_API_SRC = ROOT / "apps" / "dashboard-api" / "src"

if str(DASHBOARD_API_SRC) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_API_SRC))


def _purge_conflicting_modules(package_name: str) -> None:
    loaded = sys.modules.get(package_name)
    module_file = str(getattr(loaded, "__file__", "")) if loaded is not None else ""
    if loaded is not None and "dashboard-api" not in module_file:
        for key in [name for name in list(sys.modules.keys()) if name == package_name or name.startswith(f"{package_name}.")]:
            del sys.modules[key]


for _package in ("routes", "views", "widgets"):
    _purge_conflicting_modules(_package)

from routes.views import (
    HTTPException,
    clone_view,
    create_view,
    export_shared_view_snapshot,
    export_view_snapshot,
    list_views,
    reset_view_service,
    resolve_view_widget_query,
    update_view,
)
from widgets.query_resolver import QueryResolutionError, resolve_widget_query
from widgets.widget_catalog import list_certified_widgets



def _view_spec(
    *,
    name: str,
    scope: str,
    owner_user_id: str,
    owner_role: str,
    widget_id: str,
    widget_params: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "name": name,
        "scope": scope,
        "owner": {"user_id": owner_user_id, "role": owner_role},
        "layout": {
            "columns": 12,
            "row_height": 32,
            "items": [
                {
                    "binding_id": "widget-main",
                    "x": 0,
                    "y": 0,
                    "w": 12,
                    "h": 6,
                }
            ],
        },
        "filters": {
            "time_bucket": "day",
            "provider": "claude",
        },
        "widgets": [
            {
                "binding_id": "widget-main",
                "widget_id": widget_id,
                "params": widget_params,
                "overrides": {},
            }
        ],
    }



def test_create_update_clone_does_not_mutate_certified_metric_definitions() -> None:
    reset_view_service()
    baseline_catalog = json.dumps(list_certified_widgets(), sort_keys=True)

    created = create_view(
        {
            "spec": _view_spec(
                name="Team Usage",
                scope="team",
                owner_user_id="alice",
                owner_role="Editor",
                widget_id="provider-token-split",
                widget_params={"time_bucket": "day"},
            ),
            "actor_user_id": "alice",
        }
    )

    update_spec = copy.deepcopy(created["spec"])
    update_spec["name"] = "Team Usage Updated"
    update_spec["widgets"][0]["params"] = {"time_bucket": "month"}

    updated = update_view(
        created["view_id"],
        {
            "spec": update_spec,
            "actor_user_id": "alice",
        },
    )

    cloned = clone_view(
        created["view_id"],
        {
            "name": "Team Usage Clone",
            "owner": {"user_id": "bob", "role": "Editor"},
            "actor_user_id": "bob",
        },
    )

    team_views = list_views(scope="team")

    assert created["version"] == 1
    assert updated["version"] == 2
    assert cloned["version"] == 1
    assert cloned["view_id"] != created["view_id"]
    assert cloned["cloned_from_view_id"] == created["view_id"]
    assert len(team_views["views"]) == 2

    assert "metric_lineage" not in created["spec"]["widgets"][0]
    assert json.dumps(list_certified_widgets(), sort_keys=True) == baseline_catalog



def test_validation_and_resolver_failures_are_deterministic() -> None:
    reset_view_service()

    invalid_shared_spec = _view_spec(
        name="Invalid Shared",
        scope="team",
        owner_user_id="alice",
        owner_role="Editor",
        widget_id="experimental-non-certified",
        widget_params={"time_bucket": "day"},
    )

    with pytest.raises(HTTPException) as create_error:
        create_view({"spec": invalid_shared_spec, "actor_user_id": "alice"})

    assert create_error.value.status_code == 400
    assert create_error.value.detail["code"] == "non_certified_widget"
    assert create_error.value.detail["path"] == "view_spec.widgets[0].widget_id"

    with pytest.raises(QueryResolutionError) as invalid_param_error:
        resolve_widget_query(
            {
                "binding_id": "widget-cost",
                "widget_id": "project-cost-variance",
                "params": {"time_bucket": "hour"},
            },
            actor_role="FinanceViewer",
        )

    assert invalid_param_error.value.code == "invalid_params"
    assert invalid_param_error.value.path == "widget_query.params.time_bucket"

    with pytest.raises(QueryResolutionError) as permission_error:
        resolve_widget_query(
            {
                "binding_id": "widget-cost",
                "widget_id": "project-cost-variance",
                "params": {"time_bucket": "day"},
            },
            actor_role="Viewer",
        )

    assert permission_error.value.code == "permission_denied"



def test_shared_view_payload_round_trip_is_stable_across_restart() -> None:
    reset_view_service()

    created = create_view(
        {
            "spec": _view_spec(
                name="Org Cost",
                scope="org",
                owner_user_id="finops",
                owner_role="FinanceViewer",
                widget_id="project-cost-variance",
                widget_params={"time_bucket": "month", "include_unknown_project": True},
            ),
            "actor_user_id": "finops",
        }
    )

    resolved = resolve_view_widget_query(
        created["view_id"],
        "widget-main",
        actor_role="FinanceViewer",
    )
    assert resolved["widget_id"] == "project-cost-variance"
    assert resolved["analytics_route"] == "/projects"

    with pytest.raises(HTTPException) as forbidden:
        resolve_view_widget_query(
            created["view_id"],
            "widget-main",
            actor_role="Viewer",
        )
    assert forbidden.value.status_code == 403
    assert forbidden.value.detail["code"] == "permission_denied"

    snapshot_before = export_view_snapshot()
    shared_before = export_shared_view_snapshot()

    reset_view_service(snapshot=snapshot_before)

    snapshot_after = export_view_snapshot()
    shared_after = export_shared_view_snapshot()

    assert snapshot_before == snapshot_after
    assert shared_before == shared_after
    assert json.loads(shared_before) == json.loads(shared_after)
