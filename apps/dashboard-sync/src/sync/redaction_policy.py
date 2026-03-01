from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SENSITIVE_IDENTIFIER_KEYS: frozenset[str] = frozenset(
    {
        "user_id",
        "created_by",
        "updated_by",
        "local_user_id",
        "local_machine_id",
        "machine_id",
        "device_id",
        "hostname",
        "host_id",
        "session_id",
        "workspace_path",
        "local_path",
        "file_path",
        "home_directory",
    }
)


@dataclass(frozen=True)
class RedactionResult:
    payload: dict[str, Any]
    redacted_paths: tuple[str, ...]
    allowlisted_sensitive_paths: tuple[str, ...]



def _normalize_allowlist(allowlist: Iterable[str] | None) -> set[str]:
    if allowlist is None:
        return set()

    normalized: set[str] = set()
    for item in allowlist:
        value = str(item).strip()
        if value:
            normalized.add(value)
    return normalized



def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in SENSITIVE_IDENTIFIER_KEYS:
        return True

    if normalized.startswith("local_"):
        return True

    if normalized.endswith("_path"):
        return True

    return normalized.endswith("_machine") or normalized.endswith("_hostname")



def _join_path(path_parts: Sequence[str]) -> str:
    return ".".join(path_parts)



def redact_view_payload(
    payload: Mapping[str, Any],
    *,
    allowlist: Iterable[str] | None = None,
) -> RedactionResult:
    """Redact local sensitive identifiers unless explicitly allowlisted.

    The allowlist accepts either exact dotted paths (e.g. ``spec.owner.user_id``)
    or key-level entries (e.g. ``user_id``) for explicit release.
    """

    allowed = _normalize_allowlist(allowlist)
    redacted_paths: list[str] = []
    allowlisted_sensitive_paths: list[str] = []

    def walk(value: Any, path: tuple[str, ...]) -> Any:
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for key, nested in value.items():
                key_text = str(key)
                child_path = (*path, key_text)
                dotted = _join_path(child_path)

                if _is_sensitive_key(key_text):
                    if dotted in allowed or key_text in allowed:
                        allowlisted_sensitive_paths.append(dotted)
                        sanitized[key_text] = walk(nested, child_path)
                    else:
                        redacted_paths.append(dotted)
                    continue

                sanitized[key_text] = walk(nested, child_path)
            return sanitized

        if isinstance(value, list):
            return [walk(item, (*path, str(index))) for index, item in enumerate(value)]

        if isinstance(value, tuple):
            return [walk(item, (*path, str(index))) for index, item in enumerate(value)]

        return value

    sanitized_payload = walk(dict(payload), tuple())

    return RedactionResult(
        payload=sanitized_payload,
        redacted_paths=tuple(sorted(set(redacted_paths))),
        allowlisted_sensitive_paths=tuple(sorted(set(allowlisted_sensitive_paths))),
    )
