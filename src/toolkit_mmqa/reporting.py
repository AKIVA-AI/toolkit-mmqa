"""Report generation and diff utilities for scan results.

Provides summary statistics from scan results and comparison of two scan results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .envelope import file_descriptor, is_envelope, unwrap

SCAN_KIND = "mmqa.scan"


@dataclass(frozen=True)
class ReportSummary:
    """Summary statistics from a scan result.

    Attributes:
        unique_file_count: Files that have no byte-identical copy.
        unique_content_count: Distinct file contents (each duplicate group
            counts once), i.e. the file count after exact deduplication.
    """

    file_count: int
    total_bytes: int
    duplicate_group_count: int
    duplicate_file_count: int
    unique_file_count: int
    avg_file_size: float
    largest_group_size: int
    unique_content_count: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "duplicate_group_count": self.duplicate_group_count,
            "duplicate_file_count": self.duplicate_file_count,
            "unique_file_count": self.unique_file_count,
            "unique_content_count": self.unique_content_count,
            "avg_file_size": round(self.avg_file_size, 2),
            "largest_group_size": self.largest_group_size,
        }


@dataclass(frozen=True)
class DiffResult:
    """File-level comparison of two scan results.

    Attributes:
        added_files: Paths present in the new scan but not the old one.
        removed_files: Paths present in the old scan but not the new one.
        modified_files: Paths present in both whose SHA-256 differs.
        unchanged_file_count: Paths present in both with the same SHA-256.
        added_duplicate_groups: Duplicate groups only in the new scan.
        removed_duplicate_groups: Duplicate groups only in the old scan.
        unchanged_duplicate_groups: Duplicate groups in both scans.
    """

    added_files: list[str]
    removed_files: list[str]
    modified_files: list[str]
    unchanged_file_count: int
    added_duplicate_groups: list[list[str]]
    removed_duplicate_groups: list[list[str]]
    unchanged_duplicate_groups: list[list[str]]

    def to_json(self) -> dict[str, Any]:
        return {
            "added_files": list(self.added_files),
            "removed_files": list(self.removed_files),
            "modified_files": list(self.modified_files),
            "unchanged_file_count": self.unchanged_file_count,
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
        unique_content_count=file_count - dup_file_count + len(duplicates),
    )


def _file_hashes(scan_data: dict[str, Any], label: str) -> dict[str, str]:
    """Return ``{path: sha256}`` from a scan's per-file manifest.

    Raises:
        ValueError: If the scan has no ``files`` manifest (older scan format).
    """
    files = scan_data.get("files")
    if not isinstance(files, dict):
        raise ValueError(
            f"{label} scan has no per-file manifest ('files'); "
            "re-run 'toolkit-mmqa scan' with this version to produce one"
        )
    return {str(path): str(entry["sha256"]) for path, entry in files.items()}


def diff_scans(old_data: dict[str, Any], new_data: dict[str, Any]) -> DiffResult:
    """Compare two scan results file by file.

    Files are matched by relative path. A path in only one scan is added or
    removed; a path in both with a different SHA-256 is modified. Duplicate
    groups are compared as sets of paths.

    Args:
        old_data: Previous scan result dict.
        new_data: Current scan result dict.

    Returns:
        DiffResult with added, removed and modified files and duplicate-group changes.

    Raises:
        ValueError: If either scan lacks the per-file manifest.
    """
    old_files = _file_hashes(old_data, "Old")
    new_files = _file_hashes(new_data, "New")

    common = old_files.keys() & new_files.keys()
    modified = sorted(p for p in common if old_files[p] != new_files[p])

    old_by_key = {_group_key(g): g for g in old_data["duplicates"]}
    new_by_key = {_group_key(g): g for g in new_data["duplicates"]}

    added_keys = new_by_key.keys() - old_by_key.keys()
    removed_keys = old_by_key.keys() - new_by_key.keys()
    unchanged_keys = old_by_key.keys() & new_by_key.keys()

    return DiffResult(
        added_files=sorted(new_files.keys() - old_files.keys()),
        removed_files=sorted(old_files.keys() - new_files.keys()),
        modified_files=modified,
        unchanged_file_count=len(common) - len(modified),
        added_duplicate_groups=[new_by_key[k] for k in sorted(added_keys)],
        removed_duplicate_groups=[old_by_key[k] for k in sorted(removed_keys)],
        unchanged_duplicate_groups=[old_by_key[k] for k in sorted(unchanged_keys)],
    )


def load_scan_file(path: Path) -> dict[str, Any]:
    """Load a scan result JSON file.

    Accepts a report envelope of kind ``mmqa.scan`` (the default output since
    1.0) or the legacy bare scan object (``--format legacy-json``).

    Args:
        path: Path to JSON file.

    Returns:
        The scan result dict (the envelope's ``predicate.details``).

    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file is not valid JSON.
        KeyError: If required keys are missing.
        ValueError: If the file is a report envelope of another tool or kind.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("scan file must contain a JSON object")
    if is_envelope(data):
        data = unwrap(data, SCAN_KIND)
    # Validate required keys
    for key in ("file_count", "total_bytes", "duplicates"):
        if key not in data:
            raise KeyError(f"Missing required key in scan file: {key}")
    return data


def scan_subject(path: Path) -> list[dict[str, Any]]:
    """Subject of the scan stored at *path*.

    For an envelope this is its own subject (the dataset). For a legacy scan
    file it is the file itself.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if is_envelope(data) and isinstance(data.get("subject"), list) and data["subject"]:
        return [dict(s) for s in data["subject"]]
    return [file_descriptor(path, name=path.name)]


def _group_key(group: list[str]) -> str:
    """Create a hashable key for a duplicate group."""
    return "|".join(sorted(group))
