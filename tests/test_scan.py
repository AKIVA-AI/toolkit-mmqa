from __future__ import annotations

import json
from pathlib import Path

from toolkit_mmqa.cli import main


def test_scan_detects_duplicates(tmp_path: Path) -> None:
    root = tmp_path / "ds"
    root.mkdir()
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "b.txt").write_text("same", encoding="utf-8")
    out = tmp_path / "r.json"
    assert main(["scan", "--root", str(root), "--out", str(out)]) == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["file_count"] == 2
    assert rep["duplicates"]

