"""Directory scanner for exact-duplicate file detection.

Walks a directory tree, computes SHA-256 hashes for every file, and groups
files with identical hashes into duplicate groups.  Supports extension
filtering, maximum file-size limits, symlink handling, and an optional
progress bar.

Each scan result includes **provenance metadata** (timestamp, tool version,
scanned root path) so that downstream consumers can trace the origin of
a report.
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._version import __version__ as _TOOL_VERSION
from .hashing import sha256_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanMetadata:
    """Provenance metadata attached to every scan result.

    Captures *when* and *how* a scan was produced so that reports can be
    traced back to a specific tool version and dataset root.

    Attributes:
        tool_version: Version string of toolkit-mmqa that produced this scan.
        scanned_root: Absolute path of the directory that was scanned.
        timestamp: ISO-8601 UTC timestamp of when the scan completed.
        extensions_filter: Set of extensions used to filter files, or None.
        max_file_size: Maximum file-size limit applied, or None.
    """

    tool_version: str
    scanned_root: str
    timestamp: str
    extensions_filter: tuple[str, ...] | None = None
    max_file_size: int | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize metadata to a JSON-compatible dict."""
        result: dict[str, Any] = {
            "tool_version": self.tool_version,
            "scanned_root": self.scanned_root,
            "timestamp": self.timestamp,
        }
        if self.extensions_filter is not None:
            result["extensions_filter"] = list(self.extensions_filter)
        if self.max_file_size is not None:
            result["max_file_size"] = self.max_file_size
        return result


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning a directory for duplicate files.

    Attributes:
        file_count: Number of files successfully hashed.
        total_bytes: Sum of sizes (in bytes) of all hashed files.
        duplicates: Groups of relative file paths sharing the same SHA-256.
        skipped_count: Files skipped due to I/O errors.
        skipped_oversized: Files skipped because they exceeded max_file_size.
        skipped_symlinks: Symlinks skipped when follow_symlinks was False.
        metadata: Provenance metadata for this scan.
        files: Per-file manifest mapping each hashed file's relative path
            (POSIX separators on every platform) to
            ``{"sha256": <hex digest>, "size": <bytes>}``. Used by ``diff``
            to report added, removed and modified files.
    """

    file_count: int
    total_bytes: int
    duplicates: list[list[str]]
    skipped_count: int = 0
    skipped_oversized: int = 0
    skipped_symlinks: int = 0
    metadata: ScanMetadata | None = None
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Convert scan result to JSON-serializable dict.

        Returns:
            Dictionary with all scan fields suitable for ``json.dumps``.
        """
        result: dict[str, Any] = {
            "file_count": int(self.file_count),
            "total_bytes": int(self.total_bytes),
            "duplicates": [list(g) for g in self.duplicates],
            "skipped_count": int(self.skipped_count),
            "skipped_oversized": int(self.skipped_oversized),
            "skipped_symlinks": int(self.skipped_symlinks),
            "files": {path: dict(entry) for path, entry in sorted(self.files.items())},
        }
        if self.metadata is not None:
            result["metadata"] = self.metadata.to_json()
        return result


def _write_progress(current: int, total: int) -> None:
    """Write a progress indicator to stderr."""
    if total == 0:
        return
    pct = current * 100 // total
    bar_width = 30
    filled = bar_width * current // total
    bar = "#" * filled + "-" * (bar_width - filled)
    sys.stderr.write(f"\r[{bar}] {pct}% ({current}/{total})")
    sys.stderr.flush()


def _with_progress(items: Any, total: int, enabled: bool) -> Any:
    """Yield *items*, drawing a progress bar on stderr when *enabled*."""
    for idx, item in enumerate(items):
        if enabled and total > 0:
            _write_progress(idx, total)
        yield item


def scan(
    *,
    root: Path,
    extensions: set[str] | None = None,
    max_file_size: int | None = None,
    follow_symlinks: bool = False,
    progress: bool = False,
    workers: int = 1,
) -> ScanResult:
    """Scan directory recursively for duplicate files.

    Args:
        root: Root directory to scan
        extensions: Set of file extensions to scan (None = all files)
        max_file_size: Maximum file size in bytes to process (None = no limit).
            Files exceeding this limit are skipped.
        follow_symlinks: If False, symlinks are skipped. Default False.
        progress: If True, display a progress bar on stderr.
        workers: Number of threads hashing files in parallel (SHA-256 releases
            the GIL, so threads help on fast storage). Results do not depend on it.

    Returns:
        ScanResult with file count, total bytes, and duplicate groups

    Raises:
        PermissionError: If directory is not readable
        OSError: If filesystem errors occur
    """
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Scan root directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Scan root is not a directory: {root}")
    if max_file_size is not None and max_file_size < 0:
        raise ValueError(f"max_file_size must be >= 0, got {max_file_size}")
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")

    hashes: dict[str, list[str]] = defaultdict(list)
    files: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    file_count = 0
    skipped_count = 0
    skipped_oversized = 0
    skipped_symlinks = 0

    try:
        all_files = sorted(x for x in root.rglob("*") if x.is_file())
    except PermissionError as e:
        logger.error(f"Permission denied accessing directory: {e}")
        raise

    # Phase 1: filter (symlinks, extensions, size).
    candidates: list[tuple[Path, int]] = []
    for p in all_files:
        if p.is_symlink() and not follow_symlinks:
            logger.debug(f"Skipping symlink: {p.name}")
            skipped_symlinks += 1
            continue

        if extensions is not None and p.suffix.lower().lstrip(".") not in extensions:
            continue

        try:
            file_size = p.stat().st_size
        except OSError as e:
            logger.warning(f"Skipping file {p.name}: {e}")
            skipped_count += 1
            continue
        if max_file_size is not None and file_size > max_file_size:
            logger.debug(f"Skipping oversized file ({file_size} bytes): {p.name}")
            skipped_oversized += 1
            continue
        candidates.append((p, file_size))

    # Phase 2: hash, in input order (optionally on a thread pool).
    def _hash(p: Path) -> str | OSError:
        try:
            return sha256_file(p)
        except OSError as e:  # includes PermissionError
            return e

    total_files = len(candidates)
    paths = [p for p, _ in candidates]
    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            digests: Any = pool.map(_hash, paths)
            digests = list(_with_progress(digests, total_files, progress))
    else:
        digests = list(_with_progress(map(_hash, paths), total_files, progress))

    for (p, file_size), h in zip(candidates, digests, strict=True):
        if isinstance(h, OSError):
            logger.warning(f"Skipping file {p.name}: {h}")
            skipped_count += 1
            continue
        rel = p.relative_to(root).as_posix()
        hashes[h].append(rel)
        files[rel] = {"sha256": h, "size": file_size}
        file_count += 1
        total_bytes += file_size

    if progress and total_files > 0:
        _write_progress(total_files, total_files)
        sys.stderr.write("\n")
        sys.stderr.flush()

    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} files due to errors")
    if skipped_oversized > 0:
        logger.info(f"Skipped {skipped_oversized} files exceeding size limit")
    if skipped_symlinks > 0:
        logger.info(f"Skipped {skipped_symlinks} symlinks")

    dupes = [paths for paths in hashes.values() if len(paths) > 1]
    dupes.sort(key=lambda g: (-len(g), g[0]))

    logger.debug(f"Found {len(dupes)} duplicate groups")

    # Build provenance metadata
    meta = ScanMetadata(
        tool_version=_TOOL_VERSION,
        scanned_root=str(root),
        timestamp=datetime.now(timezone.utc).isoformat(),
        extensions_filter=tuple(sorted(extensions)) if extensions else None,
        max_file_size=max_file_size,
    )

    return ScanResult(
        file_count=file_count,
        total_bytes=total_bytes,
        duplicates=dupes,
        skipped_count=skipped_count,
        skipped_oversized=skipped_oversized,
        skipped_symlinks=skipped_symlinks,
        metadata=meta,
        files=files,
    )
