"""CLI integration tests — Task 4.

End-to-end tests exercising the full CLI pipeline: scan, report, diff, --version.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from toolkit_mmqa import __version__
from toolkit_mmqa.cli import EXIT_CLI_ERROR, EXIT_SUCCESS, main

# ============================================================================
# --version flag (Task 1)
# ============================================================================


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """--version prints version and exits."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_version_via_subprocess() -> None:
    """--version works via the actual entry point."""
    result = subprocess.run(
        [sys.executable, "-m", "toolkit_mmqa", "--version"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1] / "src"),
    )
    # --version causes SystemExit(0) which __main__.py converts to exit 0
    assert __version__ in result.stdout


# ============================================================================
# Full scan workflow
# ============================================================================


def test_cli_scan_stdout_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Scan prints valid JSON to stdout when --out is not given."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("hello", encoding="utf-8")
    (d / "b.txt").write_text("hello", encoding="utf-8")

    code = main(["scan", "--root", str(d)])
    assert code == EXIT_SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["file_count"] == 2
    assert len(data["duplicates"]) == 1


def test_cli_scan_to_file_and_report(tmp_path: Path) -> None:
    """Full pipeline: scan to file, then generate report from it."""
    d = tmp_path / "data"
    d.mkdir()
    for i in range(5):
        (d / f"f{i}.txt").write_text(f"content{i % 2}", encoding="utf-8")

    scan_out = tmp_path / "scan.json"
    code = main(["scan", "--root", str(d), "--out", str(scan_out)])
    assert code == EXIT_SUCCESS
    assert scan_out.exists()

    report_out = tmp_path / "report.json"
    code = main(["report", "--input", str(scan_out), "--out", str(report_out)])
    assert code == EXIT_SUCCESS
    assert report_out.exists()

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["file_count"] == 5
    assert report["duplicate_group_count"] > 0


def test_cli_diff_two_scans(tmp_path: Path) -> None:
    """Diff command compares two scan result files."""
    # First scan
    d1 = tmp_path / "v1"
    d1.mkdir()
    (d1 / "a.txt").write_text("same", encoding="utf-8")
    (d1 / "b.txt").write_text("same", encoding="utf-8")
    scan1 = tmp_path / "scan1.json"
    main(["scan", "--root", str(d1), "--out", str(scan1)])

    # Second scan with more files
    d2 = tmp_path / "v2"
    d2.mkdir()
    (d2 / "a.txt").write_text("same", encoding="utf-8")
    (d2 / "b.txt").write_text("same", encoding="utf-8")
    (d2 / "c.txt").write_text("unique", encoding="utf-8")
    scan2 = tmp_path / "scan2.json"
    main(["scan", "--root", str(d2), "--out", str(scan2)])

    diff_out = tmp_path / "diff.json"
    code = main(["diff", "--old", str(scan1), "--new", str(scan2), "--out", str(diff_out)])
    assert code == EXIT_SUCCESS

    diff_data = json.loads(diff_out.read_text(encoding="utf-8"))
    assert diff_data["added_files"] == 1


# ============================================================================
# Error cases
# ============================================================================


def test_cli_report_nonexistent_file() -> None:
    """Report command fails gracefully for nonexistent input."""
    code = main(["report", "--input", "/nonexistent/scan.json"])
    assert code == EXIT_CLI_ERROR


def test_cli_diff_nonexistent_old(tmp_path: Path) -> None:
    """Diff command fails when old file doesn't exist."""
    new = tmp_path / "new.json"
    new.write_text('{"file_count":0,"total_bytes":0,"duplicates":[]}', encoding="utf-8")
    code = main(["diff", "--old", "/nonexistent.json", "--new", str(new)])
    assert code == EXIT_CLI_ERROR


def test_cli_report_invalid_json(tmp_path: Path) -> None:
    """Report command fails on invalid JSON."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json!", encoding="utf-8")
    code = main(["report", "--input", str(bad)])
    assert code == EXIT_CLI_ERROR


def test_cli_scan_with_extensions_filter(tmp_path: Path) -> None:
    """Scan with --extensions filters correctly end-to-end."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("text", encoding="utf-8")
    (d / "b.jpg").write_bytes(b"\xff\xd8\xff")
    (d / "c.png").write_bytes(b"\x89PNG")

    out = tmp_path / "scan.json"
    code = main(["scan", "--root", str(d), "--extensions", "txt", "--out", str(out)])
    assert code == EXIT_SUCCESS
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["file_count"] == 1


def test_cli_scan_verbose_no_crash(tmp_path: Path) -> None:
    """Verbose mode doesn't cause crashes."""
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    code = main(["--verbose", "scan", "--root", str(tmp_path)])
    assert code == EXIT_SUCCESS


# ============================================================================
# Report to stdout
# ============================================================================


def test_cli_report_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Report prints to stdout when --out is not given."""
    scan_file = tmp_path / "scan.json"
    scan_file.write_text(
        json.dumps({"file_count": 10, "total_bytes": 1000, "duplicates": [["a", "b"]]}),
        encoding="utf-8",
    )
    code = main(["report", "--input", str(scan_file)])
    assert code == EXIT_SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["file_count"] == 10
    assert data["duplicate_group_count"] == 1


def test_cli_diff_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Diff prints to stdout when --out is not given."""
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(
        json.dumps({"file_count": 2, "total_bytes": 100, "duplicates": [["a", "b"]]}),
        encoding="utf-8",
    )
    new.write_text(
        json.dumps(
            {
                "file_count": 3,
                "total_bytes": 150,
                "duplicates": [["a", "b"], ["c", "d"]],
            }
        ),
        encoding="utf-8",
    )
    code = main(["diff", "--old", str(old), "--new", str(new)])
    assert code == EXIT_SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["added_files"] == 1
    assert len(data["added_duplicate_groups"]) == 1
