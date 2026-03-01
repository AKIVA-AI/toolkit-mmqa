"""Tests for multimodal-dataset-qa enhancements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolkit_mmqa.cli import EXIT_CLI_ERROR, EXIT_SUCCESS, main, validate_directory_path
from toolkit_mmqa.scanner import scan

# ============================================================================
# Path Validation Tests
# ============================================================================


def test_validate_directory_path_success(tmp_path: Path) -> None:
    """Test directory validation succeeds with valid directory."""
    result = validate_directory_path(tmp_path)
    assert result.is_absolute()
    assert result.is_dir()


def test_validate_directory_path_not_found() -> None:
    """Test directory validation fails with non-existent directory."""
    with pytest.raises(FileNotFoundError, match="Directory not found"):
        validate_directory_path(Path("/nonexistent"))


def test_validate_directory_path_is_file(tmp_path: Path) -> None:
    """Test directory validation fails when path is a file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        validate_directory_path(file_path)


# ============================================================================
# Scanner Tests
# ============================================================================


def test_scan_empty_directory(tmp_path: Path) -> None:
    """Test scanning empty directory."""
    result = scan(root=tmp_path)
    assert result.file_count == 0
    assert result.total_bytes == 0
    assert len(result.duplicates) == 0


def test_scan_single_file(tmp_path: Path) -> None:
    """Test scanning directory with single file."""
    (tmp_path / "file.txt").write_text("content", encoding="utf-8")

    result = scan(root=tmp_path)
    assert result.file_count == 1
    assert result.total_bytes == 7  # "content" = 7 bytes
    assert len(result.duplicates) == 0


def test_scan_detects_duplicates(tmp_path: Path) -> None:
    """Test scanner detects duplicate files."""
    content = "duplicate content"
    (tmp_path / "file1.txt").write_text(content, encoding="utf-8")
    (tmp_path / "file2.txt").write_text(content, encoding="utf-8")
    (tmp_path / "file3.txt").write_text("unique", encoding="utf-8")

    result = scan(root=tmp_path)
    assert result.file_count == 3
    assert len(result.duplicates) == 1
    assert len(result.duplicates[0]) == 2


def test_scan_nested_directories(tmp_path: Path) -> None:
    """Test scanner handles nested directories."""
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir1" / "file1.txt").write_text("test", encoding="utf-8")
    (tmp_path / "dir2").mkdir()
    (tmp_path / "dir2" / "file2.txt").write_text("test", encoding="utf-8")

    result = scan(root=tmp_path)
    assert result.file_count == 2
    assert len(result.duplicates) == 1


def test_scan_extension_filter(tmp_path: Path) -> None:
    """Test scanner filters by extension."""
    (tmp_path / "file1.txt").write_text("test", encoding="utf-8")
    (tmp_path / "file2.jpg").write_text("test", encoding="utf-8")
    (tmp_path / "file3.png").write_text("test", encoding="utf-8")

    result = scan(root=tmp_path, extensions={"txt"})
    assert result.file_count == 1

    result = scan(root=tmp_path, extensions={"jpg", "png"})
    assert result.file_count == 2


def test_scan_extension_case_insensitive(tmp_path: Path) -> None:
    """Test extension filtering is case-insensitive."""
    (tmp_path / "file1.TXT").write_text("test", encoding="utf-8")
    (tmp_path / "file2.txt").write_text("test", encoding="utf-8")

    result = scan(root=tmp_path, extensions={"txt"})
    assert result.file_count == 2


def test_scan_result_to_json(tmp_path: Path) -> None:
    """Test ScanResult.to_json() produces valid JSON."""
    (tmp_path / "file.txt").write_text("test", encoding="utf-8")

    result = scan(root=tmp_path)
    json_data = result.to_json()

    assert "file_count" in json_data
    assert "total_bytes" in json_data
    assert "duplicates" in json_data
    assert isinstance(json_data["duplicates"], list)


def test_scan_duplicate_sorting(tmp_path: Path) -> None:
    """Test duplicates are sorted by group size (descending)."""
    # Create 3 duplicates of content A
    for i in range(3):
        (tmp_path / f"a{i}.txt").write_text("content_a", encoding="utf-8")

    # Create 2 duplicates of content B
    for i in range(2):
        (tmp_path / f"b{i}.txt").write_text("content_b", encoding="utf-8")

    result = scan(root=tmp_path)
    assert len(result.duplicates) == 2
    # Group with 3 files should come first
    assert len(result.duplicates[0]) == 3
    assert len(result.duplicates[1]) == 2


# ============================================================================
# CLI Tests
# ============================================================================


def test_cli_scan_success(tmp_path: Path) -> None:
    """Test CLI scan command succeeds."""
    (tmp_path / "file.txt").write_text("test", encoding="utf-8")

    exit_code = main(["scan", "--root", str(tmp_path)])
    assert exit_code == EXIT_SUCCESS


def test_cli_scan_to_file(tmp_path: Path, capsys) -> None:
    """Test CLI scan command writes to file."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file.txt").write_text("test", encoding="utf-8")

    out_file = tmp_path / "report.json"
    exit_code = main(["scan", "--root", str(data_dir), "--out", str(out_file)])

    assert exit_code == EXIT_SUCCESS
    assert out_file.exists()

    report = json.loads(out_file.read_text())
    assert report["file_count"] == 1


def test_cli_scan_with_extensions(tmp_path: Path) -> None:
    """Test CLI scan with extension filter."""
    (tmp_path / "file1.txt").write_text("test", encoding="utf-8")
    (tmp_path / "file2.jpg").write_text("test", encoding="utf-8")

    exit_code = main(["scan", "--root", str(tmp_path), "--extensions", "txt"])
    assert exit_code == EXIT_SUCCESS


def test_cli_scan_nonexistent_directory() -> None:
    """Test CLI scan fails with non-existent directory."""
    exit_code = main(["scan", "--root", "/nonexistent/path"])
    assert exit_code == EXIT_CLI_ERROR


def test_cli_scan_file_instead_of_directory(tmp_path: Path) -> None:
    """Test CLI scan fails when given a file instead of directory."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("test", encoding="utf-8")

    exit_code = main(["scan", "--root", str(file_path)])
    assert exit_code == EXIT_CLI_ERROR


def test_cli_verbose_flag(tmp_path: Path, caplog) -> None:
    """Test --verbose flag enables debug logging."""
    (tmp_path / "file.txt").write_text("test", encoding="utf-8")

    exit_code = main(["--verbose", "scan", "--root", str(tmp_path)])
    assert exit_code == EXIT_SUCCESS


def test_cli_scan_empty_extensions(tmp_path: Path) -> None:
    """Test CLI scan with empty extensions scans all files."""
    (tmp_path / "file1.txt").write_text("test", encoding="utf-8")
    (tmp_path / "file2.jpg").write_text("test", encoding="utf-8")

    exit_code = main(["scan", "--root", str(tmp_path), "--extensions", ""])
    assert exit_code == EXIT_SUCCESS


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_scan_zero_byte_files(tmp_path: Path) -> None:
    """Test scanner handles zero-byte files."""
    (tmp_path / "empty1.txt").write_text("", encoding="utf-8")
    (tmp_path / "empty2.txt").write_text("", encoding="utf-8")

    result = scan(root=tmp_path)
    assert result.file_count == 2
    assert result.total_bytes == 0
    # Two empty files are duplicates
    assert len(result.duplicates) == 1


def test_scan_large_number_of_files(tmp_path: Path) -> None:
    """Test scanner handles many files."""
    for i in range(100):
        (tmp_path / f"file{i}.txt").write_text(f"content{i % 10}", encoding="utf-8")

    result = scan(root=tmp_path)
    assert result.file_count == 100


def test_scan_deeply_nested_directories(tmp_path: Path) -> None:
    """Test scanner handles deeply nested directories."""
    current = tmp_path
    for i in range(10):
        current = current / f"level{i}"
        current.mkdir()

    (current / "file.txt").write_text("test", encoding="utf-8")

    result = scan(root=tmp_path)
    assert result.file_count == 1


def test_scan_special_characters_in_filenames(tmp_path: Path) -> None:
    """Test scanner handles special characters in filenames."""
    (tmp_path / "file with spaces.txt").write_text("test", encoding="utf-8")
    (tmp_path / "file-with-dashes.txt").write_text("test", encoding="utf-8")
    (tmp_path / "file_with_underscores.txt").write_text("test", encoding="utf-8")

    result = scan(root=tmp_path)
    assert result.file_count == 3


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_workflow_with_duplicates(tmp_path: Path) -> None:
    """Test full workflow: create files, scan, detect duplicates."""
    # Setup
    data_dir = tmp_path / "dataset"
    data_dir.mkdir()
    (data_dir / "copy").mkdir()

    # Create duplicate images
    image_content = b"\x89PNG\r\n\x1a\n"
    (data_dir / "image1.png").write_bytes(image_content)
    (data_dir / "copy" / "image1_copy.png").write_bytes(image_content)

    # Create unique file
    (data_dir / "unique.txt").write_text("unique content", encoding="utf-8")

    # Scan
    result = scan(root=data_dir)

    # Verify
    assert result.file_count == 3
    assert len(result.duplicates) == 1
    assert len(result.duplicates[0]) == 2
