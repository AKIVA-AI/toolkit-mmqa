from __future__ import annotations

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import sha256_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning a directory for duplicate files."""

    file_count: int
    total_bytes: int
    duplicates: list[list[str]]
    skipped_count: int = 0
    skipped_oversized: int = 0
    skipped_symlinks: int = 0

    def to_json(self) -> dict[str, Any]:
        """Convert scan result to JSON-serializable dict."""
        return {
            "file_count": int(self.file_count),
            "total_bytes": int(self.total_bytes),
            "duplicates": [list(g) for g in self.duplicates],
            "skipped_count": int(self.skipped_count),
            "skipped_oversized": int(self.skipped_oversized),
            "skipped_symlinks": int(self.skipped_symlinks),
        }


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


def scan(
    *,
    root: Path,
    extensions: set[str] | None = None,
    max_file_size: int | None = None,
    follow_symlinks: bool = True,
    progress: bool = False,
) -> ScanResult:
    """Scan directory recursively for duplicate files.

    Args:
        root: Root directory to scan
        extensions: Set of file extensions to scan (None = all files)
        max_file_size: Maximum file size in bytes to process (None = no limit).
            Files exceeding this limit are skipped.
        follow_symlinks: If False, symlinks are skipped. Default True.
        progress: If True, display a progress bar on stderr.

    Returns:
        ScanResult with file count, total bytes, and duplicate groups

    Raises:
        PermissionError: If directory is not readable
        OSError: If filesystem errors occur
    """
    root = root.resolve()
    hashes: dict[str, list[str]] = defaultdict(list)
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

    total_files = len(all_files)

    for idx, p in enumerate(all_files):
        if progress and total_files > 0:
            _write_progress(idx, total_files)

        # Symlink handling
        if p.is_symlink() and not follow_symlinks:
            logger.debug(f"Skipping symlink: {p.name}")
            skipped_symlinks += 1
            continue

        if extensions is not None and p.suffix.lower().lstrip(".") not in extensions:
            continue

        try:
            file_size = p.stat().st_size

            # Max file size check
            if max_file_size is not None and file_size > max_file_size:
                logger.debug(f"Skipping oversized file ({file_size} bytes): {p.name}")
                skipped_oversized += 1
                continue

            h = sha256_file(p)
            hashes[h].append(str(p.relative_to(root)))
            file_count += 1
            total_bytes += file_size
        except (PermissionError, OSError) as e:
            logger.warning(f"Skipping file {p.name}: {e}")
            skipped_count += 1
            continue

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

    return ScanResult(
        file_count=file_count,
        total_bytes=total_bytes,
        duplicates=dupes,
        skipped_count=skipped_count,
        skipped_oversized=skipped_oversized,
        skipped_symlinks=skipped_symlinks,
    )
