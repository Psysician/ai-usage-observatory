from __future__ import annotations

import sys

from fastapi import FastAPI


def _purge_conflicting_modules(package_name: str) -> None:
    loaded = sys.modules.get(package_name)
    module_file = str(getattr(loaded, "__file__", "")) if loaded is not None else ""
    if loaded is not None and "dashboard-api" not in module_file:
        for key in [
            name
            for name in list(sys.modules.keys())
            if name == package_name or name.startswith(f"{package_name}.")
        ]:
            del sys.modules[key]


_purge_conflicting_modules("routes")

from routes.views import router as views_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Usage Observatory - Dashboard API", version="0.1.0")
    app.include_router(views_router)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
