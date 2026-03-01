from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CORE_SRC = ROOT / "apps/observability-core" / "src"
API_SRC = ROOT / "apps/observability-api" / "src"

for source_path in (str(CORE_SRC), str(API_SRC)):
    if source_path not in sys.path:
        sys.path.insert(0, source_path)


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

from routes.memory_insights import get_memory_insights


def _project_resolver(path: Path) -> str:
    return path.parent.name or "unknown"


def _assert_no_forbidden_keys(value: Any) -> None:
    forbidden_keys = {"content", "raw_content", "memory_body", "raw_memory_text"}
    if isinstance(value, dict):
        for key, nested_value in value.items():
            assert key not in forbidden_keys
            _assert_no_forbidden_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _assert_no_forbidden_keys(nested_value)


def test_memory_insights_returns_growth_and_churn_trends_by_project(tmp_path: Path) -> None:
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()

    file_a = project_a / "notes.md"
    file_b = project_b / "notes.md"
    file_a.write_text("alpha", encoding="utf-8")
    file_b.write_text("beta", encoding="utf-8")

    first_scan_time = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    first_response = get_memory_insights(
        memory_file_paths=[file_a, file_b],
        project_resolver=_project_resolver,
        scan_time=first_scan_time,
    )

    file_a.write_text("alpha\nalpha-grew", encoding="utf-8")
    second_scan_time = first_scan_time + timedelta(hours=2)
    second_response = get_memory_insights(
        memory_file_paths=[file_a, file_b],
        history_snapshots=[first_response["snapshot"]],
        project_resolver=_project_resolver,
        scan_time=second_scan_time,
    )

    projects = {project["project_id"]: project for project in second_response["projects"]}
    assert set(projects.keys()) == {"project-a", "project-b"}

    project_a_payload = projects["project-a"]
    assert len(project_a_payload["trend"]) == 2
    assert project_a_payload["growth"]["bytes_delta"] > 0
    assert project_a_payload["growth"]["direction"] == "up"
    assert project_a_payload["churn"]["changed_files_total"] >= 1


def test_memory_insights_never_leaks_raw_memory_content(tmp_path: Path) -> None:
    secret_memory_text = "TOP_SECRET_MEMORY_PAYLOAD"
    project_dir = tmp_path / "project-secret"
    project_dir.mkdir()

    memory_file = project_dir / "memory.md"
    memory_file.write_text(secret_memory_text, encoding="utf-8")

    response = get_memory_insights(
        memory_file_paths=[memory_file],
        project_resolver=_project_resolver,
        scan_time=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
    )

    payload = json.dumps(response, sort_keys=True)
    assert secret_memory_text not in payload

    first_file = response["snapshot"]["files"][0]
    assert "file_path_hash" in first_file
    assert "file_size_bytes" in first_file
    assert "scan_status" in first_file
    assert "path" not in first_file
    _assert_no_forbidden_keys(response)


def test_memory_insights_marks_missing_files_with_freshness_and_error_metadata(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project-missing"
    project_dir.mkdir()

    existing_file = project_dir / "memory.md"
    missing_file = project_dir / "does-not-exist.md"
    existing_file.write_text("known", encoding="utf-8")

    response = get_memory_insights(
        memory_file_paths=[existing_file, missing_file],
        project_resolver=_project_resolver,
        scan_time=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
    )

    freshness = response["freshness"]
    assert freshness["freshness_state"] == "partial"
    assert freshness["unavailable_files"] == 1
    assert "file_not_found" in freshness["error_codes"]

    project_payload = {project["project_id"]: project for project in response["projects"]}
    latest = project_payload["project-missing"]["trend"][-1]
    assert latest["unavailable_file_count"] == 1
