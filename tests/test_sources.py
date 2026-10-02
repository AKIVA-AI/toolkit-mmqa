"""Record sources: files and Hugging Face Hub datasets (hf:NAME[:CONFIG]:SPLIT)."""

from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

from toolkit_mmqa.cli import main
from toolkit_mmqa.sources import HubSpec, parse_hf_spec, parse_source

QUESTION = (
    "A robe takes 2 bolts of blue fiber and half that much white fiber. "
    "How many bolts in total does it take?"
)


def test_parse_hf_spec_forms() -> None:
    assert parse_hf_spec("hf:openai/gsm8k:main:test@abc123") == HubSpec(
        "openai/gsm8k", "main", "test", "abc123"
    )
    assert parse_hf_spec("hf:cais/mmlu:test") == HubSpec("cais/mmlu", None, "test", None)
    for bad in ("hf:only", "hf:a:b:c:d", "hf::test", "hf:a:"):
        with pytest.raises(ValueError):
            parse_hf_spec(bad)


def test_parse_source_names() -> None:
    assert parse_source("gsm=hf:openai/gsm8k:main:test").name == "gsm"
    assert parse_source("hf:openai/gsm8k:main:test").name == "openai/gsm8k:main:test"
    src = parse_source("t=data/train.jsonl")
    assert (src.name, src.path) == ("t", Path("data/train.jsonl"))
    assert parse_source("data/train.jsonl").name == "train.jsonl"


class _FakeDatasets(types.ModuleType):
    def __init__(self, rows: list[dict]) -> None:
        super().__init__("datasets")
        self.rows = rows
        self.calls: list[tuple] = []

    def load_dataset(self, path, name=None, *, split, revision=None, streaming=False):
        self.calls.append((path, name, split, revision, streaming))
        return iter(self.rows)


def test_cli_contamination_with_hub_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [{"id": "t0", "question": QUESTION}, {"id": "t1", "question": "clean question here"}]
    fake = _FakeDatasets(rows)
    monkeypatch.setitem(sys.modules, "datasets", fake)
    train = tmp_path / "train.jsonl"
    train.write_text(json.dumps({"question": "Copied: " + QUESTION}) + "\n", encoding="utf-8")
    out = tmp_path / "c.json"
    code = main(
        ["contamination", "--train", str(train), "--benchmark", "gsm=hf:org/bench:main:test@v1"]
        + ["--field", "question", "--id-field", "id", "--out", str(out)]
    )
    assert code == 1
    assert fake.calls == [("org/bench", "main", "test", "v1", True)]
    report = json.loads(out.read_bytes())
    (subject,) = report["subject"]
    # Digest: SHA-256 over one canonical JSON line per record, computed independently.
    lines = b"".join(
        json.dumps(
            {"id": r["id"], "index": i, "text": r["question"]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
        for i, r in enumerate(rows)
    )
    assert subject == {
        "name": "gsm",
        "uri": "hf://datasets/org/bench",
        "digest": {"sha256": hashlib.sha256(lines).hexdigest()},
        "annotations": {"split": "test", "config": "main", "revision": "v1", "records_read": 2},
    }
    (row,) = report["predicate"]["details"]["contaminated_records"]
    assert row["id"] == "t0"


def test_cli_hub_source_without_extra_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "datasets", None)  # import fails
    train = tmp_path / "train.jsonl"
    train.write_text('{"text": "x"}\n', encoding="utf-8")
    assert main(["contamination", "--train", str(train), "--eval", "hf:a/b:test"]) == 2


def test_cli_hub_missing_field_writes_error_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "datasets", _FakeDatasets([{"other": "x"}]))
    out = tmp_path / "d.json"
    code = main(["dedup", "--input", "hf:a/b:train", "--out", str(out)])
    assert code == 2
    report = json.loads(out.read_bytes())
    assert report["predicate"]["verdict"] == "error"
    assert "hf:a/b:train[0]: missing field 'text'" in report["predicate"]["details"]["error"]


def test_dedup_write_deduped_rejects_hub_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "datasets", _FakeDatasets([]))
    assert main(["dedup", "--input", "hf:a/b:train", "--write-deduped", "x.jsonl"]) == 2


def test_real_datasets_library_reads_local_dataset(tmp_path: Path) -> None:
    """End to end with the real `datasets` library on a local JSONL dataset folder."""
    pytest.importorskip("datasets")
    ds_dir = tmp_path / "local_ds"
    ds_dir.mkdir()
    (ds_dir / "test.jsonl").write_text(
        json.dumps({"text": "hello world"}) + "\n" + json.dumps({"text": "Hello, World!"}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "d.json"
    code = main(["dedup", "--input", f"hf:{ds_dir}:test", "--out", str(out)])
    assert code == 0
    summary = json.loads(out.read_bytes())["predicate"]["summary"]
    assert summary["record_count"] == 2
    assert summary["exact_duplicate_count"] == 1
