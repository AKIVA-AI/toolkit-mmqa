"""Report generation and diff utilities for scan results.

Provides summary statistics from scan results and comparison of two scan results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReportSummary:
    """Summary statistics from a scan result."""

    file_count: int
    total_bytes: int
    duplicate_group_count: int
    duplicate_file_count: int
    unique_file_count: int
    avg_file_size: float
    largest_group_size: int

    def to_json(self) -> dict[str, Any]:
        return {
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "duplicate_group_count": self.duplicate_group_count,
            "duplicate_file_count": self.duplicate_file_count,
            "unique_file_count": self.unique_file_count,
            "avg_file_size": round(self.avg_file_size, 2),
            "largest_group_size": self.largest_group_size,
        }


@dataclass(frozen=True)
class DiffResult:
    """Comparison of two scan results."""

    added_files: int
    removed_files: int
    added_duplicate_groups: list[list[str]]
    removed_duplicate_groups: list[list[str]]
    unchanged_duplicate_groups: list[list[str]]

    def to_json(self) -> dict[str, Any]:
        return {
            "added_files": self.added_files,
            "removed_files": self.removed_files,
            "added_duplicate_groups": self.added_duplicate_groups,
            "removed_duplicate_groups": self.removed_duplicate_groups,
            "unchanged_duplicate_groups": self.unchanged_duplicate_groups,
        }


def generate_report(scan_data: dict[str, Any]) -> ReportSummary:
    """Generate summary statistics from a scan result dict.

    Args:
        scan_data: Scan result as loaded from JSON (must have file_count,
                   total_bytes, duplicates keys).

    Returns:
        ReportSummary with computed statistics.

    Raises:
        KeyError: If required keys are missing from scan_data.
    """
    file_count = scan_data["file_count"]
    total_bytes = scan_data["total_bytes"]
    duplicates = scan_data["duplicates"]

    dup_file_count = sum(len(g) for g in duplicates)
    largest = max((len(g) for g in duplicates), default=0)
    avg_size = total_bytes / file_count if file_count > 0 else 0.0

    return ReportSummary(
        file_count=file_count,
        total_bytes=total_bytes,
        duplicate_group_count=len(duplicates),
        duplicate_file_count=dup_file_count,
        unique_file_count=file_count - dup_file_count,
        avg_file_size=avg_size,
        largest_group_size=largest,
    )


def diff_scans(old_data: dict[str, Any], new_data: dict[str, Any]) -> DiffResult:
    """Compare two scan results and identify changes in duplicates.

    Args:
        old_data: Previous scan result dict.
        new_data: Current scan result dict.

    Returns:
        DiffResult showing added, removed, and unchanged duplicate groups.
    """
    old_groups = {_group_key(g) for g in old_data["duplicates"]}
    new_groups = {_group_key(g) for g in new_data["duplicates"]}

    old_by_key = {_group_key(g): g for g in old_data["duplicates"]}
    new_by_key = {_group_key(g): g for g in new_data["duplicates"]}

    added_keys = new_groups - old_groups
    removed_keys = old_groups - new_groups
    unchanged_keys = old_groups & new_groups

    return DiffResult(
        added_files=new_data["file_count"] - old_data["file_count"],
        removed_files=max(0, old_data["file_count"] - new_data["file_count"]),
        added_duplicate_groups=[new_by_key[k] for k in sorted(added_keys)],
        removed_duplicate_groups=[old_by_key[k] for k in sorted(removed_keys)],
        unchanged_duplicate_groups=[old_by_key[k] for k in sorted(unchanged_keys)],
    )


def load_scan_file(path: Path) -> dict[str, Any]:
    """Load a scan result JSON file.

    Args:
        path: Path to JSON file.

    Returns:
        Parsed scan result dict.

    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file is not valid JSON.
        KeyError: If required keys are missing.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    # Validate required keys
    for key in ("file_count", "total_bytes", "duplicates"):
        if key not in data:
            raise KeyError(f"Missing required key in scan file: {key}")
    return data


def _group_key(group: list[str]) -> str:
    """Create a hashable key for a duplicate group."""
    return "|".join(sorted(group))
