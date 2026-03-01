from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable

ProjectResolver = Callable[[Path], str]
PathHasher = Callable[[Path], str]


@dataclass(frozen=True)
class MemoryFileFact:
    project_id: str
    file_path_hash: str
    file_size_bytes: int | None
    mtime_epoch_seconds: float | None
    scan_time_epoch_seconds: float
    freshness_state: str
    scan_status: str
    scan_error_code: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _to_epoch_seconds(scan_time: datetime | None) -> float:
    if scan_time is None:
        return datetime.now(tz=timezone.utc).timestamp()
    if scan_time.tzinfo is None:
        scan_time = scan_time.replace(tzinfo=timezone.utc)
    return scan_time.timestamp()


def _default_project_resolver(path: Path) -> str:
    parent_name = path.parent.name.strip()
    return parent_name or "unknown"


def _default_path_hasher(path: Path) -> str:
    normalized = str(path.expanduser().resolve(strict=False))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _classify_freshness(
    age_seconds: float | None,
    scan_status: str,
    live_threshold_seconds: int,
    warm_threshold_seconds: int,
) -> str:
    if scan_status != "ok":
        return "partial"
    if age_seconds is None:
        return "partial"
    if age_seconds <= live_threshold_seconds:
        return "live"
    if age_seconds <= warm_threshold_seconds:
        return "warm"
    return "stale"


def scan_memory_files(
    memory_file_paths: Iterable[str | Path],
    project_resolver: ProjectResolver | None = None,
    scan_time: datetime | None = None,
    path_hasher: PathHasher | None = None,
    live_threshold_seconds: int = 3600,
    warm_threshold_seconds: int = 86400,
) -> list[MemoryFileFact]:
    resolver = project_resolver or _default_project_resolver
    hasher = path_hasher or _default_path_hasher
    scan_epoch = _to_epoch_seconds(scan_time)

    facts: list[MemoryFileFact] = []
    for raw_path in memory_file_paths:
        path = Path(raw_path).expanduser()
        project_id = resolver(path)
        path_hash = hasher(path)

        try:
            if not path.exists():
                facts.append(
                    MemoryFileFact(
                        project_id=project_id,
                        file_path_hash=path_hash,
                        file_size_bytes=None,
                        mtime_epoch_seconds=None,
                        scan_time_epoch_seconds=scan_epoch,
                        freshness_state="partial",
                        scan_status="missing",
                        scan_error_code="file_not_found",
                    )
                )
                continue

            if not path.is_file():
                facts.append(
                    MemoryFileFact(
                        project_id=project_id,
                        file_path_hash=path_hash,
                        file_size_bytes=None,
                        mtime_epoch_seconds=None,
                        scan_time_epoch_seconds=scan_epoch,
                        freshness_state="partial",
                        scan_status="error",
                        scan_error_code="not_a_file",
                    )
                )
                continue

            stat_result = path.stat()
            mtime_epoch = float(stat_result.st_mtime)
            age_seconds = max(scan_epoch - mtime_epoch, 0.0)
            freshness = _classify_freshness(
                age_seconds=age_seconds,
                scan_status="ok",
                live_threshold_seconds=live_threshold_seconds,
                warm_threshold_seconds=warm_threshold_seconds,
            )

            facts.append(
                MemoryFileFact(
                    project_id=project_id,
                    file_path_hash=path_hash,
                    file_size_bytes=int(stat_result.st_size),
                    mtime_epoch_seconds=mtime_epoch,
                    scan_time_epoch_seconds=scan_epoch,
                    freshness_state=freshness,
                    scan_status="ok",
                    scan_error_code=None,
                )
            )
        except PermissionError:
            facts.append(
                MemoryFileFact(
                    project_id=project_id,
                    file_path_hash=path_hash,
                    file_size_bytes=None,
                    mtime_epoch_seconds=None,
                    scan_time_epoch_seconds=scan_epoch,
                    freshness_state="partial",
                    scan_status="error",
                    scan_error_code="permission_denied",
                )
            )
        except OSError:
            facts.append(
                MemoryFileFact(
                    project_id=project_id,
                    file_path_hash=path_hash,
                    file_size_bytes=None,
                    mtime_epoch_seconds=None,
                    scan_time_epoch_seconds=scan_epoch,
                    freshness_state="partial",
                    scan_status="error",
                    scan_error_code="os_error",
                )
            )

    return facts


def build_scan_snapshot(
    memory_file_paths: Iterable[str | Path],
    project_resolver: ProjectResolver | None = None,
    scan_time: datetime | None = None,
    path_hasher: PathHasher | None = None,
    live_threshold_seconds: int = 3600,
    warm_threshold_seconds: int = 86400,
) -> dict[str, object]:
    facts = scan_memory_files(
        memory_file_paths=memory_file_paths,
        project_resolver=project_resolver,
        scan_time=scan_time,
        path_hasher=path_hasher,
        live_threshold_seconds=live_threshold_seconds,
        warm_threshold_seconds=warm_threshold_seconds,
    )

    captured_at = _to_epoch_seconds(scan_time)
    if facts:
        captured_at = facts[0].scan_time_epoch_seconds

    return {
        "captured_at_epoch_seconds": captured_at,
        "files": [fact.to_dict() for fact in facts],
    }
