from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AttributionResult:
    project_id: str
    confidence: float
    reason_code: str
    evidence: str


def _clean_project(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "unknown":
        return None
    return text


def _extract_project_from_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    normalized = path_value.replace("\\", "/")
    markers = ["/repos/", "/workspace/", "/workspaces/"]
    for marker in markers:
        if marker in normalized:
            candidate = normalized.split(marker, 1)[1].split("/", 1)[0]
            cleaned = _clean_project(candidate)
            if cleaned:
                return cleaned
    path_obj = Path(normalized)
    basename = _clean_project(path_obj.name)
    if path_obj.suffix.lower() in {".json", ".jsonl", ".log", ".txt"}:
        return None
    if basename and basename not in {"src", "app", "apps", "tmp", "home"}:
        return basename
    return None


def resolve_project_attribution(
    *,
    explicit_project_id: str | None = None,
    session_id: str | None = None,
    source_path: str | None = None,
    workspace_path: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    session_project_map: Mapping[str, str] | None = None,
    workspace_project_map: Mapping[str, str] | None = None,
    path_project_map: Mapping[str, str] | None = None,
    unknown_project_id: str = "unknown",
) -> AttributionResult:
    normalized_metadata = metadata or {}
    normalized_session_map = session_project_map or {}
    normalized_workspace_map = workspace_project_map or {}
    normalized_path_map = path_project_map or {}

    explicit = _clean_project(explicit_project_id)
    if explicit:
        return AttributionResult(
            project_id=explicit,
            confidence=1.0,
            reason_code="explicit_project_marker",
            evidence="explicit project id field",
        )

    metadata_fields = (
        "project_id",
        "project",
        "repo",
        "repository",
        "repo_name",
        "workspace_project",
    )
    for field in metadata_fields:
        candidate = _clean_project(normalized_metadata.get(field))
        if candidate:
            return AttributionResult(
                project_id=candidate,
                confidence=0.95,
                reason_code="metadata_project_marker",
                evidence=f"metadata:{field}",
            )

    if session_id:
        mapped_session_project = _clean_project(normalized_session_map.get(session_id))
        if mapped_session_project:
            return AttributionResult(
                project_id=mapped_session_project,
                confidence=0.9,
                reason_code="session_linkage_map",
                evidence=f"session_id:{session_id}",
            )

    candidate_paths = [path for path in (workspace_path, source_path) if path]
    for candidate_path in candidate_paths:
        mapped_workspace_project = _clean_project(
            normalized_workspace_map.get(candidate_path)
        )
        if mapped_workspace_project:
            return AttributionResult(
                project_id=mapped_workspace_project,
                confidence=0.85,
                reason_code="workspace_path_map",
                evidence=f"workspace:{candidate_path}",
            )

    for candidate_path in candidate_paths:
        for prefix, mapped_project in sorted(normalized_path_map.items()):
            if candidate_path.startswith(prefix):
                cleaned_project = _clean_project(mapped_project)
                if cleaned_project:
                    return AttributionResult(
                        project_id=cleaned_project,
                        confidence=0.75,
                        reason_code="path_prefix_map",
                        evidence=f"path_prefix:{prefix}",
                    )

    for candidate_path in candidate_paths:
        heuristic = _extract_project_from_path(candidate_path)
        if heuristic:
            return AttributionResult(
                project_id=heuristic,
                confidence=0.6,
                reason_code="path_heuristic",
                evidence=f"path:{candidate_path}",
            )

    return AttributionResult(
        project_id=unknown_project_id,
        confidence=0.0,
        reason_code="unknown_fallback",
        evidence="no attribution signals",
    )
