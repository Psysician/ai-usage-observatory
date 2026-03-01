from __future__ import annotations

import sys

from fastapi import FastAPI


def _purge_conflicting_modules(package_name: str) -> None:
    loaded = sys.modules.get(package_name)
    module_file = str(getattr(loaded, "__file__", "")) if loaded is not None else ""
    if loaded is not None and "observability-api" not in module_file:
        for key in [
            name
            for name in list(sys.modules.keys())
            if name == package_name or name.startswith(f"{package_name}.")
        ]:
            del sys.modules[key]


_purge_conflicting_modules("routes")

from routes.memory_insights import router as memory_router
from routes.metrics import router as metrics_router
from routes.projects import router as projects_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Usage Observatory - Observability API", version="0.1.0")
    app.include_router(metrics_router)
    app.include_router(projects_router)
    if memory_router is not None:
        app.include_router(memory_router)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
