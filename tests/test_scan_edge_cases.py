"""Edge case tests for scanner — Task 3.

Covers: empty directories, symlinks, large files, binary files,
permission errors (where possible), and other edge scenarios.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from toolkit_mmqa.scanner import ScanResult, scan

# ============================================================================
# Empty directory variants
# ============================================================================


def test_scan_completely_empty_dir(tmp_path: Path) -> None:
    """Empty root with no files or subdirs."""
    result = scan(root=tmp_path)
    assert result.file_count == 0
    assert result.total_bytes == 0
    assert result.duplicates == []


def test_scan_nested_empty_dirs(tmp_path: Path) -> None:
    """Nested subdirectories containing no files."""
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    (tmp_path / "x" / "y").mkdir(parents=True)
    result = scan(root=tmp_path)
    assert result.file_count == 0


def test_scan_mix_empty_and_populated_dirs(tmp_path: Path) -> None:
    """Some subdirs empty, some with files."""
    (tmp_path / "empty").mkdir()
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "file.txt").write_text("data", encoding="utf-8")
    result = scan(root=tmp_path)
    assert result.file_count == 1


# ============================================================================
# Symlinks
# ============================================================================


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks unreliable on Windows CI")
def test_scan_follows_file_symlink(tmp_path: Path) -> None:
    """Scanner should handle file symlinks (rglob follows them by default)."""
    real = tmp_path / "real.txt"
    real.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    result = scan(root=tmp_path)
    # Both real file and symlink are enumerated
    assert result.file_count == 2
    # They have same content so they are duplicates
    assert len(result.duplicates) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks unreliable on Windows CI")
def test_scan_broken_symlink(tmp_path: Path) -> None:
    """Scanner should skip broken symlinks gracefully."""
    link = tmp_path / "broken_link.txt"
    link.symlink_to(tmp_path / "nonexistent.txt")
    (tmp_path / "real.txt").write_text("data", encoding="utf-8")

    result = scan(root=tmp_path)
    # Only the real file should be counted
    assert result.file_count == 1


# ============================================================================
# Large files
# ============================================================================


def test_scan_large_file(tmp_path: Path) -> None:
    """Scanner handles a file larger than the hashing chunk size (1MB)."""
    large = tmp_path / "large.bin"
    # Write 2MB of data
    large.write_bytes(b"\x00" * (2 * 1024 * 1024))
    result = scan(root=tmp_path)
    assert result.file_count == 1
    assert result.total_bytes == 2 * 1024 * 1024


def test_scan_duplicate_large_files(tmp_path: Path) -> None:
    """Two identical large files are detected as duplicates."""
    content = os.urandom(1024 * 512)  # 512KB
    (tmp_path / "a.bin").write_bytes(content)
    (tmp_path / "b.bin").write_bytes(content)
    result = scan(root=tmp_path)
    assert len(result.duplicates) == 1


# ============================================================================
# Binary files
# ============================================================================


def test_scan_binary_files(tmp_path: Path) -> None:
    """Scanner handles binary files with null bytes."""
    (tmp_path / "bin1.dat").write_bytes(b"\x00\x01\x02\xff")
    (tmp_path / "bin2.dat").write_bytes(b"\x00\x01\x02\xff")
    (tmp_path / "bin3.dat").write_bytes(b"\xff\xfe\xfd")
    result = scan(root=tmp_path)
    assert result.file_count == 3
    assert len(result.duplicates) == 1


def test_scan_mixed_text_and_binary(tmp_path: Path) -> None:
    """Scanner processes both text and binary files in same directory."""
    (tmp_path / "text.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    result = scan(root=tmp_path)
    assert result.file_count == 2
    assert len(result.duplicates) == 0


# ============================================================================
# ScanResult serialization
# ============================================================================


def test_scan_result_roundtrip(tmp_path: Path) -> None:
    """ScanResult.to_json() produces correct types for JSON serialization."""
    (tmp_path / "a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "b.txt").write_text("same", encoding="utf-8")
    result = scan(root=tmp_path)
    j = result.to_json()
    assert isinstance(j["file_count"], int)
    assert isinstance(j["total_bytes"], int)
    assert isinstance(j["duplicates"], list)
    for group in j["duplicates"]:
        assert isinstance(group, list)
        for item in group:
            assert isinstance(item, str)


def test_scan_result_frozen() -> None:
    """ScanResult is immutable."""
    r = ScanResult(file_count=0, total_bytes=0, duplicates=[])
    with pytest.raises(AttributeError):
        r.file_count = 5  # type: ignore[misc]


# ============================================================================
# Extension edge cases
# ============================================================================


def test_scan_no_extension_files(tmp_path: Path) -> None:
    """Files without extensions are included when no filter is set."""
    (tmp_path / "Makefile").write_text("all:", encoding="utf-8")
    (tmp_path / "README").write_text("hi", encoding="utf-8")
    result = scan(root=tmp_path)
    assert result.file_count == 2


def test_scan_dotfiles(tmp_path: Path) -> None:
    """Hidden dotfiles are included in scan."""
    (tmp_path / ".hidden").write_text("secret", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.pyc", encoding="utf-8")
    result = scan(root=tmp_path)
    assert result.file_count == 2


def test_scan_multiple_dots_in_filename(tmp_path: Path) -> None:
    """Files with multiple dots use only final suffix for extension filter."""
    (tmp_path / "archive.tar.gz").write_bytes(b"\x1f\x8b" + b"\x00" * 10)
    result = scan(root=tmp_path, extensions={"gz"})
    assert result.file_count == 1
    result2 = scan(root=tmp_path, extensions={"tar"})
    assert result2.file_count == 0
