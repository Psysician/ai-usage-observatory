from __future__ import annotations

from typing import Any, Mapping

from views.view_model import ViewValidationError
from views.view_service import InMemoryViewService, ViewNotFoundError
from widgets.query_resolver import QueryResolutionError, resolve_widget_query
from widgets.widget_catalog import get_certified_widget_ids, list_certified_widgets

try:
    from fastapi import APIRouter, HTTPException, Query
except Exception:  # pragma: no cover - fallback runtime for minimal environments
    class APIRouter:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.routes: list[tuple[str, str, Any]] = []

        def get(self, path: str, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                self.routes.append(("GET", path, func))
                return func

            return decorator

        def post(self, path: str, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                self.routes.append(("POST", path, func))
                return func

            return decorator

        def put(self, path: str, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                self.routes.append(("PUT", path, func))
                return func

            return decorator

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: Any) -> None:
            super().__init__(str(detail))
            self.status_code = status_code
            self.detail = detail

    def Query(default: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        return default


router = APIRouter(prefix="", tags=["views"])



def _new_service() -> InMemoryViewService:
    return InMemoryViewService(certified_widget_ids=get_certified_widget_ids())


_view_service = _new_service()



def get_view_service() -> InMemoryViewService:
    return _view_service



def reset_view_service(snapshot: str | Mapping[str, Any] | None = None) -> InMemoryViewService:
    global _view_service
    _view_service = _new_service()
    if snapshot is not None:
        _view_service.load_snapshot(snapshot)
    return _view_service



def export_view_snapshot() -> str:
    return _view_service.export_snapshot()



def export_shared_view_snapshot() -> str:
    return _view_service.export_shared_snapshot()



def _extract_spec(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if "spec" in payload:
        candidate = payload["spec"]
    else:
        candidate = payload

    if not isinstance(candidate, Mapping):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_type",
                "path": "payload.spec",
                "message": "Expected object payload for view spec.",
            },
        )
    return candidate



def _normalize_optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None



def _to_http_exception(error: Exception) -> HTTPException:
    if isinstance(error, ViewNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "code": "view_not_found",
                "path": "view_id",
                "message": str(error),
            },
        )

    if isinstance(error, QueryResolutionError):
        status_code = 403 if error.code == "permission_denied" else 400
        return HTTPException(status_code=status_code, detail=error.as_dict())

    if isinstance(error, ViewValidationError):
        return HTTPException(status_code=400, detail=error.as_dict())

    return HTTPException(
        status_code=400,
        detail={"code": "invalid_request", "path": "request", "message": str(error)},
    )


@router.get("/widgets/certified")
def get_certified_widget_catalog() -> dict[str, Any]:
    return {"widgets": list_certified_widgets()}


@router.get("/views")
def list_views(
    scope: str | None = Query(None),
    owner_user_id: str | None = Query(None),
) -> dict[str, Any]:
    return {
        "views": _view_service.list_views(
            scope=_normalize_optional_str(scope),
            owner_user_id=_normalize_optional_str(owner_user_id),
        )
    }


@router.post("/views")
def create_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        spec = _extract_spec(payload)
        actor_user_id = payload.get("actor_user_id") if isinstance(payload, Mapping) else None
        return _view_service.create_view(spec, actor_user_id=actor_user_id)
    except Exception as error:  # pragma: no cover - exercised in integration tests
        raise _to_http_exception(error) from error


@router.put("/views/{view_id}")
def update_view(view_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        spec = _extract_spec(payload)
        actor_user_id = payload.get("actor_user_id") if isinstance(payload, Mapping) else None
        return _view_service.update_view(view_id, spec, actor_user_id=actor_user_id)
    except Exception as error:  # pragma: no cover - exercised in integration tests
        raise _to_http_exception(error) from error


@router.post("/views/{view_id}/clone")
def clone_view(view_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body = dict(payload or {})
    try:
        return _view_service.clone_view(
            view_id,
            name=body.get("name"),
            owner=body.get("owner") if isinstance(body.get("owner"), Mapping) else None,
            scope=body.get("scope"),
            actor_user_id=body.get("actor_user_id"),
        )
    except Exception as error:  # pragma: no cover - exercised in integration tests
        raise _to_http_exception(error) from error


@router.post("/views/{view_id}/widgets/{binding_id}/resolve")
def resolve_view_widget_query(
    view_id: str,
    binding_id: str,
    payload: Mapping[str, Any] | None = None,
    actor_role: str = Query("Viewer"),
) -> dict[str, Any]:
    body = dict(payload or {})

    try:
        view = _view_service.get_view(view_id)
        binding = next(
            (
                widget
                for widget in view["spec"]["widgets"]
                if widget.get("binding_id") == binding_id
            ),
            None,
        )
        if binding is None:
            raise ViewNotFoundError(f"{view_id}:{binding_id}")

        override_params = body.get("params")
        if override_params is not None:
            if not isinstance(override_params, Mapping):
                raise QueryResolutionError(
                    code="invalid_type",
                    path="payload.params",
                    message="payload.params must be an object.",
                )
            merged_binding = dict(binding)
            merged_binding["params"] = {
                **dict(binding.get("params", {})),
                **dict(override_params),
            }
        else:
            merged_binding = dict(binding)

        capabilities = body.get("actor_capabilities")
        actor_caps = capabilities if isinstance(capabilities, list) else None
        resolved_role = _normalize_optional_str(actor_role) or "Viewer"

        return resolve_widget_query(
            merged_binding,
            actor_role=resolved_role,
            actor_capabilities=actor_caps,
        )
    except Exception as error:  # pragma: no cover - exercised in integration tests
        raise _to_http_exception(error) from error
