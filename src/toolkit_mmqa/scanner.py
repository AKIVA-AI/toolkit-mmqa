from __future__ import annotations

import logging
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

    def to_json(self) -> dict[str, Any]:
        """Convert scan result to JSON-serializable dict."""
        return {
            "file_count": int(self.file_count),
            "total_bytes": int(self.total_bytes),
            "duplicates": [list(g) for g in self.duplicates],
        }


def scan(*, root: Path, extensions: set[str] | None = None) -> ScanResult:
    """Scan directory recursively for duplicate files.

    Args:
        root: Root directory to scan
        extensions: Set of file extensions to scan (None = all files)

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

    try:
        all_files = sorted(x for x in root.rglob("*") if x.is_file())
    except PermissionError as e:
        logger.error(f"Permission denied accessing directory: {e}")
        raise

    for p in all_files:
        if extensions is not None and p.suffix.lower().lstrip(".") not in extensions:
            continue

        try:
            file_size = p.stat().st_size
            h = sha256_file(p)
            hashes[h].append(str(p.relative_to(root)))
            file_count += 1
            total_bytes += file_size
        except (PermissionError, OSError) as e:
            logger.warning(f"Skipping file {p.name}: {e}")
            skipped_count += 1
            continue

    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} files due to errors")

    dupes = [paths for paths in hashes.values() if len(paths) > 1]
    dupes.sort(key=lambda g: (-len(g), g[0]))

    logger.debug(f"Found {len(dupes)} duplicate groups")

    return ScanResult(file_count=file_count, total_bytes=total_bytes, duplicates=dupes)
