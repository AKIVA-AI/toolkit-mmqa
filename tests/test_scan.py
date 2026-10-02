from __future__ import annotations

import json
from pathlib import Path

from helpers import payload

from toolkit_mmqa.cli import main


def test_scan_detects_duplicates(tmp_path: Path) -> None:
    root = tmp_path / "ds"
    root.mkdir()
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "b.txt").write_text("same", encoding="utf-8")
    out = tmp_path / "r.json"
    assert main(["scan", "--root", str(root), "--out", str(out)]) == 0
    rep = payload(json.loads(out.read_text(encoding="utf-8")))
    assert rep["file_count"] == 2
    assert rep["duplicates"]


def test_scan_output_includes_per_file_manifest(tmp_path: Path) -> None:
    """Every hashed file is listed with its SHA-256 and size."""
    import hashlib

    root = tmp_path / "ds"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"same")
    (root / "sub" / "b.txt").write_bytes(b"other!")
    out = tmp_path / "r.json"
    assert main(["scan", "--root", str(root), "--out", str(out)]) == 0
    rep = payload(json.loads(out.read_text(encoding="utf-8")))
    files = rep["files"]
    assert set(files) == {"a.txt", "sub/b.txt"}  # POSIX separators on every OS
    assert files["a.txt"] == {"sha256": hashlib.sha256(b"same").hexdigest(), "size": 4}
    assert files["sub/b.txt"]["size"] == 6


def test_scan_manifest_excludes_skipped_files(tmp_path: Path) -> None:
    """Oversized or filtered-out files are not in the manifest."""
    root = tmp_path / "ds"
    root.mkdir()
    (root / "small.txt").write_bytes(b"x")
    (root / "big.txt").write_bytes(b"x" * 100)
    (root / "img.png").write_bytes(b"png")
    out = tmp_path / "r.json"
    code = main(
        [
            "scan",
            "--root",
            str(root),
            "--out",
            str(out),
            "--extensions",
            "txt",
            "--max-file-size",
            "10",
        ]
    )
    assert code == 0
    rep = payload(json.loads(out.read_text(encoding="utf-8")))
    assert list(rep["files"]) == ["small.txt"]


def test_cli_diff_detects_file_swap(tmp_path: Path) -> None:
    """End to end: swapping two files' contents shows up as two modified files."""
    v1 = tmp_path / "v1"
    v2 = tmp_path / "v2"
    v1.mkdir()
    v2.mkdir()
    (v1 / "a.txt").write_text("alpha", encoding="utf-8")
    (v1 / "b.txt").write_text("beta", encoding="utf-8")
    (v2 / "a.txt").write_text("beta", encoding="utf-8")
    (v2 / "b.txt").write_text("alpha", encoding="utf-8")
    s1, s2, d = tmp_path / "s1.json", tmp_path / "s2.json", tmp_path / "d.json"
    assert main(["scan", "--root", str(v1), "--out", str(s1)]) == 0
    assert main(["scan", "--root", str(v2), "--out", str(s2)]) == 0
    assert main(["diff", "--old", str(s1), "--new", str(s2), "--out", str(d)]) == 0
    diff = payload(json.loads(d.read_text(encoding="utf-8")))
    assert diff["modified_files"] == ["a.txt", "b.txt"]
    assert diff["added_files"] == []
    assert diff["removed_files"] == []


def test_cli_diff_rejects_scan_without_manifest(tmp_path: Path) -> None:
    """A scan file without a per-file manifest is a CLI error, not a silent count diff."""
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps({"file_count": 1, "total_bytes": 1, "duplicates": []}), encoding="utf-8"
    )
    assert main(["diff", "--old", str(legacy), "--new", str(legacy)]) == 2


def test_parallel_hashing_gives_identical_result(tmp_path: Path) -> None:
    from toolkit_mmqa.scanner import scan

    root = tmp_path / "ds"
    (root / "sub").mkdir(parents=True)
    for i in range(40):
        (root / ("sub" if i % 3 else ".") / f"f{i}.bin").write_bytes(bytes([i % 7]) * (i + 1))
    one = scan(root=root, workers=1).to_json()
    many = scan(root=root, workers=4).to_json()
    one.pop("metadata"), many.pop("metadata")
    assert one == many
    assert one["file_count"] == 40


def test_workers_must_be_positive(tmp_path: Path) -> None:
    assert main(["scan", "--root", str(tmp_path), "--workers", "0"]) == 2
