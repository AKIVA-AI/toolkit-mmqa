"""Record-level deduplication (dedup command).

Near-duplicate similarity is the MinHash estimate of the Jaccard similarity of
character-trigram sets (Broder 1997, "On the resemblance and containment of
documents"). The tests check clear-cut cases against the exact Jaccard value:
pairs with exact Jaccard >= 0.95 must be found at threshold 0.8 and pairs with
exact Jaccard <= 0.5 must not.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from toolkit_mmqa.cli import main
from toolkit_mmqa.dedup import SourceRecords, dedup_records
from toolkit_mmqa.records import Record
from toolkit_mmqa.text_dedup import _ngrams

LONG = (
    "The mitochondria is the membrane-bound organelle that generates most of the "
    "chemical energy needed to power the biochemical reactions of the cell."
)


def _src(name: str, *texts: str) -> SourceRecords:
    return SourceRecords(name, [Record(index=i, text=t) for i, t in enumerate(texts)])


def test_exact_duplicates_after_normalization_keep_first() -> None:
    result = dedup_records([_src("d", "Hello, World!", "other", "hello world", "HELLO   world.")])
    assert result.exact_groups == [
        [
            {"source": "d", "index": 0, "id": None},
            {"source": "d", "index": 2, "id": None},
            {"source": "d", "index": 3, "id": None},
        ]
    ]
    assert result.exact_duplicate_count == 2
    assert [r["index"] for r in result.removable] == [2, 3]


def test_duplicates_across_files() -> None:
    result = dedup_records([_src("a", "same text"), _src("b", "x", "Same text")])
    assert [[m["source"] for m in g] for g in result.exact_groups] == [["a", "b"]]
    assert result.removable == [{"source": "b", "index": 1, "id": None}]


def test_empty_records_are_counted_not_grouped() -> None:
    result = dedup_records([_src("d", "", "!!!", "text")])
    assert result.empty_count == 2
    assert result.exact_groups == []


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(_ngrams(a)), set(_ngrams(b))
    return len(sa & sb) / len(sa | sb)


def test_near_duplicates_match_exact_jaccard_in_clear_cases() -> None:
    rng = random.Random(11)
    words = LONG.split()
    texts = [LONG]
    for _ in range(15):
        w = list(words)
        for _ in range(rng.randint(0, 12)):
            w[rng.randrange(len(w))] = rng.choice(["alpha", "beta", "gamma", "delta"])
        texts.append(" ".join(w))
    result = dedup_records([_src("d", *texts)], near_duplicates=True, threshold=0.8)
    found = {frozenset((p["a"]["index"], p["b"]["index"])) for p in (result.near_pairs or [])}
    checked_hi = checked_lo = 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            j_exact = _jaccard(texts[i], texts[j])
            if j_exact >= 0.95:
                checked_hi += 1
                assert frozenset((i, j)) in found, (i, j, j_exact)
            elif j_exact <= 0.5:
                checked_lo += 1
                assert frozenset((i, j)) not in found, (i, j, j_exact)
    assert checked_hi and checked_lo  # both regimes exercised


def test_near_and_exact_groups_merge_transitively() -> None:
    edited = LONG.replace("most", "much")
    result = dedup_records(
        [_src("d", LONG, LONG.upper(), edited, "unrelated")], near_duplicates=True
    )
    assert [r["index"] for r in result.removable] == [1, 2]
    assert result.near_groups == [[{"source": "d", "index": i, "id": None} for i in (0, 1, 2)]]


def _jsonl(path: Path, texts: list[str]) -> Path:
    path.write_text(
        "".join(json.dumps({"id": f"r{i}", "text": t}) + "\n" for i, t in enumerate(texts)),
        encoding="utf-8",
    )
    return path


def test_cli_dedup_writes_report_and_deduped_copy(tmp_path: Path) -> None:
    data = _jsonl(tmp_path / "data.jsonl", ["a b c", "unique", "A, b c!", LONG, LONG + " x"])
    out = tmp_path / "dedup.json"
    clean = tmp_path / "clean.jsonl"
    code = main(
        ["dedup", "--input", str(data), "--id-field", "id", "--near-dup"]
        + ["--write-deduped", str(clean), "--out", str(out)]
    )
    assert code == 0
    report = json.loads(out.read_bytes())
    pred = report["predicate"]
    assert pred["kind"] == "mmqa.dedup" and pred["verdict"] == "pass"
    assert pred["summary"]["record_count"] == 5
    assert pred["summary"]["exact_duplicate_count"] == 1
    assert pred["summary"]["removable_count"] == 2
    assert pred["summary"]["kept_count"] == 3
    assert pred["details"]["exact_groups"][0][1]["id"] == "r2"
    assert report["subject"][0]["name"] == "data.jsonl"
    kept = [json.loads(line)["id"] for line in clean.read_text(encoding="utf-8").splitlines()]
    assert kept == ["r0", "r1", "r3"]
    assert pred["details"]["deduped_file"]["record_count"] == 3


def test_cli_dedup_fail_on_exact(tmp_path: Path) -> None:
    data = _jsonl(tmp_path / "data.jsonl", ["same", "same"])
    out = tmp_path / "d.json"
    code = main(["dedup", "--input", str(data), "--fail-on", "exact-duplicates", "--out", str(out)])
    assert code == 1
    assert json.loads(out.read_bytes())["predicate"]["summary"]["failed_checks"] == [
        "exact-duplicates"
    ]


@pytest.mark.parametrize(
    "extra",
    [
        ["--fail-on", "near-duplicates"],  # needs --near-dup
        ["--write-deduped", "x.jsonl", "--input", "other=placeholder"],
        ["--near-dup-threshold", "2"],
    ],
)
def test_cli_dedup_usage_errors(tmp_path: Path, extra: list[str]) -> None:
    data = _jsonl(tmp_path / "data.jsonl", ["a"])
    (tmp_path / "placeholder").write_text("x\n", encoding="utf-8")
    assert main(["dedup", "--input", str(data), *extra]) == 2


def test_cli_dedup_write_deduped_rejects_csv(tmp_path: Path) -> None:
    p = tmp_path / "d.csv"
    p.write_text("text\na\na\n", encoding="utf-8")
    assert main(["dedup", "--input", str(p), "--write-deduped", str(tmp_path / "o.csv")]) == 2
