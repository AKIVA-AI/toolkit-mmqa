"""CLI wiring for near-duplicate text detection (scan --near-dup-text)."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import payload

from toolkit_mmqa.cli import EXIT_CLI_ERROR, EXIT_SUCCESS, main

BASE = "the quick brown fox jumps over the lazy dog while the cat sleeps. " * 20


def _dataset(root: Path) -> Path:
    root.mkdir()
    (root / "a.txt").write_text(BASE, encoding="utf-8")
    # Near-duplicate: small edit, so SHA-256 differs.
    (root / "b.txt").write_text(BASE.replace("lazy", "sleepy", 1) + " end", encoding="utf-8")
    (root / "c.txt").write_text("an unrelated document about spreadsheets " * 10, encoding="utf-8")
    (root / "img.bin").write_bytes(b"\x89PNG\x00\x01\x02\xff\xfe")
    return root


def _scan(tmp_path: Path, *extra: str) -> tuple[int, dict]:
    root = _dataset(tmp_path / "ds")
    out = tmp_path / "scan.json"
    code = main(["scan", "--root", str(root), "--out", str(out), *extra])
    data = payload(json.loads(out.read_text(encoding="utf-8"))) if out.exists() else {}
    return code, data


def test_scan_near_dup_text_finds_edited_copy(tmp_path: Path) -> None:
    code, data = _scan(tmp_path, "--near-dup-text")
    assert code == EXIT_SUCCESS
    assert data["duplicates"] == []  # not byte-identical
    nd = data["near_duplicates"]
    assert nd["threshold"] == 0.8
    assert nd["groups"] == [["a.txt", "b.txt"]]
    assert nd["similarity_scores"]["a.txt|b.txt"] >= 0.8
    assert nd["text_file_count"] == 3
    assert nd["skipped_non_text"] == ["img.bin"]


def test_scan_near_dup_threshold_is_respected(tmp_path: Path) -> None:
    code, data = _scan(tmp_path, "--near-dup-text", "--near-dup-threshold", "0.999")
    assert code == EXIT_SUCCESS
    assert data["near_duplicates"]["threshold"] == 0.999
    assert data["near_duplicates"]["groups"] == []


def test_scan_without_flag_has_no_near_dup_section(tmp_path: Path) -> None:
    code, data = _scan(tmp_path)
    assert code == EXIT_SUCCESS
    assert "near_duplicates" not in data


def test_scan_near_dup_threshold_out_of_range_is_error(tmp_path: Path) -> None:
    code, _ = _scan(tmp_path, "--near-dup-text", "--near-dup-threshold", "1.5")
    assert code == EXIT_CLI_ERROR


def test_scan_near_dup_threshold_without_flag_is_error(tmp_path: Path) -> None:
    code, _ = _scan(tmp_path, "--near-dup-threshold", "0.9")
    assert code == EXIT_CLI_ERROR
