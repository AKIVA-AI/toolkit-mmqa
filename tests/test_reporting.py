"""Tests for reporting module — covers report and diff."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolkit_mmqa.reporting import (
    DiffResult,
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


def _scan(files: dict[str, str], duplicates: list[list[str]] | None = None) -> dict:
    """Build a scan dict with a per-file manifest (path -> fake sha256)."""
    return {
        "file_count": len(files),
        "total_bytes": 10 * len(files),
        "duplicates": duplicates or [],
        "files": {p: {"sha256": h, "size": 10} for p, h in files.items()},
    }


def test_diff_no_changes() -> None:
    """Identical scans produce no diff."""
    data = _scan({"a": "h1", "b": "h1"}, [["a", "b"]])
    result = diff_scans(data, data)
    assert result.added_files == []
    assert result.removed_files == []
    assert result.modified_files == []
    assert result.unchanged_file_count == 2
    assert len(result.added_duplicate_groups) == 0
    assert len(result.removed_duplicate_groups) == 0
    assert len(result.unchanged_duplicate_groups) == 1


def test_diff_added_group() -> None:
    """New files and a new duplicate group appear."""
    old = _scan({"a": "h1", "b": "h1"}, [["a", "b"]])
    new = _scan({"a": "h1", "b": "h1", "c": "h2", "d": "h2"}, [["a", "b"], ["c", "d"]])
    result = diff_scans(old, new)
    assert result.added_files == ["c", "d"]
    assert result.removed_files == []
    assert len(result.added_duplicate_groups) == 1
    assert len(result.unchanged_duplicate_groups) == 1


def test_diff_removed_group() -> None:
    """Duplicate group removed."""
    old = _scan({"a": "h1", "b": "h1", "c": "h2", "d": "h2"}, [["a", "b"], ["c", "d"]])
    new = _scan({"a": "h1", "b": "h1", "c": "h2"}, [["a", "b"]])
    result = diff_scans(old, new)
    assert result.removed_files == ["d"]
    assert result.added_files == []
    assert len(result.removed_duplicate_groups) == 1


def test_diff_full_replacement_is_not_reported_as_no_change() -> None:
    """Three files replaced by three different files: 3 added, 3 removed.

    Regression: the count-based diff reported 0 added / 0 removed here.
    """
    old = _scan({"a": "h1", "b": "h2", "c": "h3"})
    new = _scan({"x": "h4", "y": "h5", "z": "h6"})
    result = diff_scans(old, new)
    assert result.added_files == ["x", "y", "z"]
    assert result.removed_files == ["a", "b", "c"]
    assert result.modified_files == []
    assert result.unchanged_file_count == 0


def test_diff_file_swap_reports_both_modified() -> None:
    """Swapping the contents of two files marks both as modified."""
    old = _scan({"a": "h1", "b": "h2", "c": "h3"})
    new = _scan({"a": "h2", "b": "h1", "c": "h3"})
    result = diff_scans(old, new)
    assert result.added_files == []
    assert result.removed_files == []
    assert result.modified_files == ["a", "b"]
    assert result.unchanged_file_count == 1


def test_diff_shrink_has_no_negative_counts() -> None:
    """Shrinking from 5 to 2 files lists the 3 removed files, never a negative add."""
    old = _scan({f"f{i}": f"h{i}" for i in range(5)})
    new = _scan({"f0": "h0", "f1": "h1"})
    result = diff_scans(old, new)
    assert result.added_files == []
    assert result.removed_files == ["f2", "f3", "f4"]
    assert result.unchanged_file_count == 2


def test_diff_requires_file_manifest() -> None:
    """Scans without a per-file manifest cannot be diffed (fail closed)."""
    legacy = {"file_count": 2, "total_bytes": 100, "duplicates": [["a", "b"]]}
    with pytest.raises(ValueError, match="per-file manifest"):
        diff_scans(legacy, _scan({"a": "h1"}))
    with pytest.raises(ValueError, match="per-file manifest"):
        diff_scans(_scan({"a": "h1"}), legacy)


def test_diff_result_to_json() -> None:
    """DiffResult serializes."""
    r = DiffResult(
        added_files=["x"],
        removed_files=[],
        modified_files=["m"],
        unchanged_file_count=3,
        added_duplicate_groups=[["x", "y"]],
        removed_duplicate_groups=[],
        unchanged_duplicate_groups=[],
    )
    j = r.to_json()
    assert j["added_files"] == ["x"]
    assert j["modified_files"] == ["m"]
    assert j["unchanged_file_count"] == 3


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


def test_report_unique_content_count_counts_one_keeper_per_group() -> None:
    """unique_content_count = distinct contents (each duplicate group counts once).

    unique_file_count keeps its meaning: files that have no duplicate at all.
    """
    data = {
        "file_count": 10,
        "total_bytes": 1000,
        "duplicates": [["a", "b", "c"], ["d", "e"]],
    }
    report = generate_report(data)
    assert report.unique_file_count == 5
    assert report.unique_content_count == 7
    assert report.to_json()["unique_content_count"] == 7
