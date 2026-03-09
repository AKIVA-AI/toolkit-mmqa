"""Tests for reporting module — covers report and diff."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolkit_mmqa.reporting import (
    DiffResult,
    ReportSummary,
    diff_scans,
    generate_report,
    load_scan_file,
)


# ============================================================================
# generate_report
# ============================================================================


def test_report_basic() -> None:
    """Basic report generation."""
    data = {
        "file_count": 10,
        "total_bytes": 5000,
        "duplicates": [["a.txt", "b.txt"], ["c.txt", "d.txt", "e.txt"]],
    }
    report = generate_report(data)
    assert report.file_count == 10
    assert report.total_bytes == 5000
    assert report.duplicate_group_count == 2
    assert report.duplicate_file_count == 5
    assert report.unique_file_count == 5
    assert report.avg_file_size == 500.0
    assert report.largest_group_size == 3


def test_report_no_duplicates() -> None:
    """Report with zero duplicates."""
    data = {"file_count": 3, "total_bytes": 300, "duplicates": []}
    report = generate_report(data)
    assert report.duplicate_group_count == 0
    assert report.duplicate_file_count == 0
    assert report.unique_file_count == 3
    assert report.largest_group_size == 0


def test_report_zero_files() -> None:
    """Report for empty scan."""
    data = {"file_count": 0, "total_bytes": 0, "duplicates": []}
    report = generate_report(data)
    assert report.avg_file_size == 0.0


def test_report_to_json() -> None:
    """Report serializes to JSON dict."""
    data = {"file_count": 1, "total_bytes": 100, "duplicates": []}
    report = generate_report(data)
    j = report.to_json()
    assert isinstance(j, dict)
    assert j["file_count"] == 1
    assert "avg_file_size" in j


def test_report_missing_key() -> None:
    """Missing key raises KeyError."""
    with pytest.raises(KeyError):
        generate_report({"file_count": 1, "total_bytes": 0})


# ============================================================================
# diff_scans
# ============================================================================


def test_diff_no_changes() -> None:
    """Identical scans produce no diff."""
    data = {"file_count": 2, "total_bytes": 100, "duplicates": [["a", "b"]]}
    result = diff_scans(data, data)
    assert result.added_files == 0
    assert result.removed_files == 0
    assert len(result.added_duplicate_groups) == 0
    assert len(result.removed_duplicate_groups) == 0
    assert len(result.unchanged_duplicate_groups) == 1


def test_diff_added_group() -> None:
    """New duplicate group appears."""
    old = {"file_count": 2, "total_bytes": 100, "duplicates": [["a", "b"]]}
    new = {"file_count": 4, "total_bytes": 200, "duplicates": [["a", "b"], ["c", "d"]]}
    result = diff_scans(old, new)
    assert result.added_files == 2
    assert len(result.added_duplicate_groups) == 1
    assert len(result.unchanged_duplicate_groups) == 1


def test_diff_removed_group() -> None:
    """Duplicate group removed."""
    old = {"file_count": 4, "total_bytes": 200, "duplicates": [["a", "b"], ["c", "d"]]}
    new = {"file_count": 3, "total_bytes": 150, "duplicates": [["a", "b"]]}
    result = diff_scans(old, new)
    assert result.removed_files == 1
    assert len(result.removed_duplicate_groups) == 1


def test_diff_result_to_json() -> None:
    """DiffResult serializes."""
    r = DiffResult(
        added_files=1,
        removed_files=0,
        added_duplicate_groups=[["x", "y"]],
        removed_duplicate_groups=[],
        unchanged_duplicate_groups=[],
    )
    j = r.to_json()
    assert j["added_files"] == 1


# ============================================================================
# load_scan_file
# ============================================================================


def test_load_scan_file_valid(tmp_path: Path) -> None:
    """Loading a valid scan file."""
    f = tmp_path / "scan.json"
    f.write_text(
        json.dumps({"file_count": 1, "total_bytes": 10, "duplicates": []}),
        encoding="utf-8",
    )
    data = load_scan_file(f)
    assert data["file_count"] == 1


def test_load_scan_file_not_found() -> None:
    """Loading nonexistent file raises error."""
    with pytest.raises(FileNotFoundError):
        load_scan_file(Path("/nonexistent/scan.json"))


def test_load_scan_file_invalid_json(tmp_path: Path) -> None:
    """Loading invalid JSON raises error."""
    f = tmp_path / "bad.json"
    f.write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_scan_file(f)


def test_load_scan_file_missing_keys(tmp_path: Path) -> None:
    """Loading file with missing keys raises KeyError."""
    f = tmp_path / "incomplete.json"
    f.write_text(json.dumps({"file_count": 1}), encoding="utf-8")
    with pytest.raises(KeyError, match="Missing required key"):
        load_scan_file(f)
