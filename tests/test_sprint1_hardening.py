"""Tests for Sprint 1 hardening features."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from toolkit_mmqa.cli import EXIT_CLI_ERROR, EXIT_SUCCESS, JSONFormatter, build_parser, main
from toolkit_mmqa.scanner import ScanResult, scan

# ============================================================================
# Task 3: Progress bar for large scans
# ============================================================================


def test_scan_progress_flag_accepted(tmp_path: Path) -> None:
    """Test that --progress flag is accepted by CLI parser."""
    parser = build_parser()
    args = parser.parse_args(["scan", "--root", str(tmp_path), "--progress"])
    assert args.progress is True


def test_scan_no_progress_by_default(tmp_path: Path) -> None:
    """Test that progress is off by default."""
    parser = build_parser()
    args = parser.parse_args(["scan", "--root", str(tmp_path)])
    assert args.progress is False


def test_scan_progress_writes_to_stderr(tmp_path: Path, capsys) -> None:
    """Test that progress output goes to stderr."""
    for i in range(5):
        (tmp_path / f"file{i}.txt").write_text(f"content{i}", encoding="utf-8")

    result = scan(root=tmp_path, progress=True)
    assert result.file_count == 5

    captured = capsys.readouterr()
    # Progress goes to stderr
    assert "[" in captured.err or "#" in captured.err


def test_scan_progress_empty_dir(tmp_path: Path, capsys) -> None:
    """Test progress with empty directory does not crash."""
    result = scan(root=tmp_path, progress=True)
    assert result.file_count == 0


def test_scan_progress_cli(tmp_path: Path) -> None:
    """Test --progress flag through CLI."""
    (tmp_path / "file.txt").write_text("test", encoding="utf-8")
    exit_code = main(["scan", "--root", str(tmp_path), "--progress"])
    assert exit_code == EXIT_SUCCESS


# ============================================================================
# Task 4: --max-file-size flag
# ============================================================================


def test_max_file_size_skips_large_files(tmp_path: Path) -> None:
    """Test that files exceeding max_file_size are skipped."""
    (tmp_path / "small.txt").write_text("small", encoding="utf-8")  # 5 bytes
    (tmp_path / "large.txt").write_text("x" * 1000, encoding="utf-8")  # 1000 bytes

    result = scan(root=tmp_path, max_file_size=100)
    assert result.file_count == 1
    assert result.skipped_oversized == 1


def test_max_file_size_none_processes_all(tmp_path: Path) -> None:
    """Test that max_file_size=None processes all files."""
    (tmp_path / "small.txt").write_text("small", encoding="utf-8")
    (tmp_path / "large.txt").write_text("x" * 1000, encoding="utf-8")

    result = scan(root=tmp_path, max_file_size=None)
    assert result.file_count == 2
    assert result.skipped_oversized == 0


def test_max_file_size_exact_boundary(tmp_path: Path) -> None:
    """Test file exactly at max_file_size is included."""
    content = "12345"  # 5 bytes
    (tmp_path / "exact.txt").write_text(content, encoding="utf-8")

    result = scan(root=tmp_path, max_file_size=5)
    assert result.file_count == 1
    assert result.skipped_oversized == 0


def test_max_file_size_boundary_exceeded(tmp_path: Path) -> None:
    """Test file one byte over max_file_size is skipped."""
    content = "123456"  # 6 bytes
    (tmp_path / "over.txt").write_text(content, encoding="utf-8")

    result = scan(root=tmp_path, max_file_size=5)
    assert result.file_count == 0
    assert result.skipped_oversized == 1


def test_max_file_size_cli_flag(tmp_path: Path) -> None:
    """Test --max-file-size flag through CLI."""
    (tmp_path / "small.txt").write_text("small", encoding="utf-8")
    (tmp_path / "large.txt").write_text("x" * 1000, encoding="utf-8")

    out_file = tmp_path / "report.json"
    exit_code = main([
        "scan", "--root", str(tmp_path),
        "--max-file-size", "100",
        "--out", str(out_file),
    ])
    assert exit_code == EXIT_SUCCESS

    report = json.loads(out_file.read_text(encoding="utf-8"))
    assert report["file_count"] == 1
    assert report["skipped_oversized"] == 1


def test_max_file_size_zero(tmp_path: Path) -> None:
    """Test max_file_size=0 skips all non-empty files."""
    (tmp_path / "file.txt").write_text("content", encoding="utf-8")

    result = scan(root=tmp_path, max_file_size=0)
    assert result.file_count == 0
    assert result.skipped_oversized == 1


# ============================================================================
# Task 5: Symlink handling (--follow-symlinks / --skip-symlinks)
# ============================================================================


@pytest.mark.skipif(os.name == "nt", reason="Symlinks require elevated privileges on Windows")
def test_skip_symlinks(tmp_path: Path) -> None:
    """Test that symlinks are skipped when follow_symlinks=False."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("content", encoding="utf-8")
    link_file = tmp_path / "link.txt"
    link_file.symlink_to(real_file)

    result = scan(root=tmp_path, follow_symlinks=False)
    assert result.file_count == 1
    assert result.skipped_symlinks == 1


@pytest.mark.skipif(os.name == "nt", reason="Symlinks require elevated privileges on Windows")
def test_follow_symlinks_default(tmp_path: Path) -> None:
    """Test that symlinks are followed by default."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("content", encoding="utf-8")
    link_file = tmp_path / "link.txt"
    link_file.symlink_to(real_file)

    result = scan(root=tmp_path, follow_symlinks=True)
    assert result.file_count == 2
    assert result.skipped_symlinks == 0


def test_skip_symlinks_cli_flag_accepted() -> None:
    """Test --skip-symlinks flag is accepted by parser."""
    parser = build_parser()
    args = parser.parse_args(["scan", "--root", "/tmp", "--skip-symlinks"])
    assert args.follow_symlinks is False


def test_follow_symlinks_cli_default() -> None:
    """Test --follow-symlinks is the default."""
    parser = build_parser()
    args = parser.parse_args(["scan", "--root", "/tmp"])
    assert args.follow_symlinks is True


def test_no_symlinks_in_normal_dir(tmp_path: Path) -> None:
    """Test that skip-symlinks mode works even with no symlinks."""
    (tmp_path / "file.txt").write_text("content", encoding="utf-8")

    result = scan(root=tmp_path, follow_symlinks=False)
    assert result.file_count == 1
    assert result.skipped_symlinks == 0


# ============================================================================
# Task 6: Structured JSON logging (--log-format json)
# ============================================================================


def test_log_format_flag_accepted() -> None:
    """Test --log-format flag is accepted by parser."""
    parser = build_parser()
    args = parser.parse_args(["--log-format", "json", "scan", "--root", "/tmp"])
    assert args.log_format == "json"


def test_log_format_default_is_text() -> None:
    """Test default log format is text."""
    parser = build_parser()
    args = parser.parse_args(["scan", "--root", "/tmp"])
    assert args.log_format == "text"


def test_json_formatter_output() -> None:
    """Test JSONFormatter produces valid JSON."""
    formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=None,
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test message"
    assert parsed["logger"] == "test"
    assert "timestamp" in parsed


def test_json_formatter_with_exception() -> None:
    """Test JSONFormatter includes exception info."""
    formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    try:
        raise ValueError("test error")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Error occurred",
        args=None,
        exc_info=exc_info,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "exception" in parsed
    assert "ValueError" in parsed["exception"]


def test_json_logging_cli(tmp_path: Path) -> None:
    """Test --log-format json through CLI."""
    (tmp_path / "file.txt").write_text("test", encoding="utf-8")
    exit_code = main(["--verbose", "--log-format", "json", "scan", "--root", str(tmp_path)])
    assert exit_code == EXIT_SUCCESS


# ============================================================================
# Task 8: Scan result signing (Ed25519)
# ============================================================================


def test_generate_keypair() -> None:
    """Test Ed25519 key pair generation."""
    from toolkit_mmqa.signing import generate_ed25519_keypair

    kp = generate_ed25519_keypair()
    assert "BEGIN PRIVATE KEY" in kp.private_key_pem
    assert "BEGIN PUBLIC KEY" in kp.public_key_pem


def test_sign_and_verify() -> None:
    """Test signing and verifying a payload."""
    from toolkit_mmqa.signing import generate_ed25519_keypair, sign_payload, verify_payload

    kp = generate_ed25519_keypair()
    payload = b"test payload"
    sig = sign_payload(payload=payload, private_key_pem=kp.private_key_pem)
    assert isinstance(sig, str)
    assert len(sig) > 0

    valid = verify_payload(
        payload=payload, signature_b64=sig, public_key_pem=kp.public_key_pem
    )
    assert valid is True


def test_verify_tampered_payload() -> None:
    """Test that tampered payload fails verification."""
    from toolkit_mmqa.signing import generate_ed25519_keypair, sign_payload, verify_payload

    kp = generate_ed25519_keypair()
    payload = b"original"
    sig = sign_payload(payload=payload, private_key_pem=kp.private_key_pem)

    valid = verify_payload(
        payload=b"tampered", signature_b64=sig, public_key_pem=kp.public_key_pem
    )
    assert valid is False


def test_canonical_json_deterministic() -> None:
    """Test canonical JSON is deterministic regardless of key order."""
    from toolkit_mmqa.signing import canonical_json_bytes

    obj1 = {"b": 2, "a": 1}
    obj2 = {"a": 1, "b": 2}
    assert canonical_json_bytes(obj1) == canonical_json_bytes(obj2)


def test_canonical_json_compact() -> None:
    """Test canonical JSON uses compact separators."""
    from toolkit_mmqa.signing import canonical_json_bytes

    result = canonical_json_bytes({"a": 1, "b": 2})
    assert result == b'{"a":1,"b":2}'


def test_sign_scan_result_cli(tmp_path: Path) -> None:
    """Test --sign flag produces signed output through CLI."""
    from toolkit_mmqa.signing import generate_ed25519_keypair

    # Setup data directory
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file.txt").write_text("test", encoding="utf-8")

    # Generate key pair
    kp = generate_ed25519_keypair()
    key_file = tmp_path / "private.pem"
    key_file.write_text(kp.private_key_pem, encoding="utf-8")
    pub_file = tmp_path / "public.pem"
    pub_file.write_text(kp.public_key_pem, encoding="utf-8")

    # Sign scan
    out_file = tmp_path / "signed_report.json"
    exit_code = main([
        "scan", "--root", str(data_dir),
        "--sign", "--sign-key", str(key_file),
        "--out", str(out_file),
    ])
    assert exit_code == EXIT_SUCCESS

    report = json.loads(out_file.read_text(encoding="utf-8"))
    assert "signature" in report
    assert len(report["signature"]) > 0


def test_verify_subcommand(tmp_path: Path) -> None:
    """Test verify subcommand validates signed scan result."""
    from toolkit_mmqa.signing import (
        canonical_json_bytes,
        generate_ed25519_keypair,
        sign_payload,
    )

    kp = generate_ed25519_keypair()
    pub_file = tmp_path / "public.pem"
    pub_file.write_text(kp.public_key_pem, encoding="utf-8")

    # Create a signed scan result
    scan_data = {"file_count": 1, "total_bytes": 4, "duplicates": []}
    payload = canonical_json_bytes(scan_data)
    sig = sign_payload(payload=payload, private_key_pem=kp.private_key_pem)
    scan_data["signature"] = sig

    scan_file = tmp_path / "signed.json"
    scan_file.write_text(json.dumps(scan_data), encoding="utf-8")

    exit_code = main(["verify", "--input", str(scan_file), "--public-key", str(pub_file)])
    assert exit_code == EXIT_SUCCESS


def test_verify_subcommand_invalid_sig(tmp_path: Path) -> None:
    """Test verify subcommand rejects invalid signature."""
    from toolkit_mmqa.signing import generate_ed25519_keypair

    kp = generate_ed25519_keypair()
    pub_file = tmp_path / "public.pem"
    pub_file.write_text(kp.public_key_pem, encoding="utf-8")

    scan_data = {"file_count": 1, "duplicates": [], "signature": "invalidbase64sig=="}
    scan_file = tmp_path / "bad.json"
    scan_file.write_text(json.dumps(scan_data), encoding="utf-8")

    exit_code = main(["verify", "--input", str(scan_file), "--public-key", str(pub_file)])
    assert exit_code == EXIT_CLI_ERROR


def test_verify_subcommand_no_signature(tmp_path: Path) -> None:
    """Test verify subcommand fails when no signature in file."""
    from toolkit_mmqa.signing import generate_ed25519_keypair

    kp = generate_ed25519_keypair()
    pub_file = tmp_path / "public.pem"
    pub_file.write_text(kp.public_key_pem, encoding="utf-8")

    scan_data = {"file_count": 1, "duplicates": []}
    scan_file = tmp_path / "unsigned.json"
    scan_file.write_text(json.dumps(scan_data), encoding="utf-8")

    exit_code = main(["verify", "--input", str(scan_file), "--public-key", str(pub_file)])
    assert exit_code == EXIT_CLI_ERROR


def test_sign_missing_key_file(tmp_path: Path) -> None:
    """Test --sign with missing key file returns error."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file.txt").write_text("test", encoding="utf-8")

    exit_code = main([
        "scan", "--root", str(data_dir),
        "--sign", "--sign-key", str(tmp_path / "nonexistent.pem"),
    ])
    assert exit_code == EXIT_CLI_ERROR


# ============================================================================
# ScanResult JSON includes new fields
# ============================================================================


def test_scan_result_json_has_skip_fields(tmp_path: Path) -> None:
    """Test ScanResult.to_json() includes skip counters."""
    result = ScanResult(
        file_count=5,
        total_bytes=100,
        duplicates=[],
        skipped_count=1,
        skipped_oversized=2,
        skipped_symlinks=3,
    )
    j = result.to_json()
    assert j["skipped_count"] == 1
    assert j["skipped_oversized"] == 2
    assert j["skipped_symlinks"] == 3


def test_scan_result_defaults_zero() -> None:
    """Test ScanResult defaults skip counters to 0."""
    result = ScanResult(file_count=0, total_bytes=0, duplicates=[])
    j = result.to_json()
    assert j["skipped_count"] == 0
    assert j["skipped_oversized"] == 0
    assert j["skipped_symlinks"] == 0
