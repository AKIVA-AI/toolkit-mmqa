"""Train/eval and benchmark contamination.

References used to validate the statistics:

* N-gram overlap follows the contamination analysis of Brown et al. (2020),
  "Language Models are Few-Shot Learners", Appendix C: an evaluation example is
  flagged when any of its 13-grams occurs in the training data. The overlap
  fraction is checked against an independent brute-force implementation of that
  definition (``_reference_overlap``) on random corpora.
* MinHash estimates Jaccard similarity (Broder 1997, "On the resemblance and
  containment of documents"). The estimate is checked against the exact Jaccard
  similarity of the character-trigram sets, within 4 standard errors
  sqrt(J(1-J)/k) (Leskovec, Rajaraman, Ullman, "Mining of Massive Datasets",
  section 3.3).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from toolkit_mmqa.cli import main
from toolkit_mmqa.contamination import (
    Target,
    check_contamination,
    normalize_tokens,
    record_ngrams,
)
from toolkit_mmqa.records import Record
from toolkit_mmqa.text_dedup import _ngrams


def _recs(*texts: str) -> list[Record]:
    return [Record(index=i, text=t) for i, t in enumerate(texts)]


def _check(train: list[str], evals: list[str], **kw):
    return check_contamination([("train", _recs(*train))], [Target("eval", _recs(*evals))], **kw)


# --- normalization and n-grams ------------------------------------------------


def test_normalize_tokens_ignores_case_punctuation_and_width() -> None:
    # NFKC folds the full-width digits and letters.
    assert normalize_tokens("What is  ２+２?  ＡNSWER: Four!") == [
        "what",
        "is",
        "2",
        "2",
        "answer",
        "four",
    ]


def test_record_ngrams_long_short_and_too_short() -> None:
    toks = [str(i) for i in range(15)]
    grams, n = record_ngrams(toks, 13, 8)
    assert n == 13 and len(grams) == 3
    grams, n = record_ngrams(toks[:9], 13, 8)
    assert n == 9 and grams == {tuple(toks[:9])}
    grams, n = record_ngrams(toks[:5], 13, 8)
    assert n is None and grams == set()


# --- worked example (GPT-3 13-gram definition) --------------------------------


def test_worked_example_single_shared_13gram() -> None:
    """A 20-token eval record has 8 distinct 13-grams; training shares exactly one."""
    eval_words = [f"e{i}" for i in range(20)]
    shared = eval_words[3:16]  # one 13-gram
    train_text = "prefix words " + " ".join(shared) + " suffix words"
    result = _check([train_text], [" ".join(eval_words)])
    (row,) = result.records
    assert row["methods"] == ["ngram"]
    assert row["ngram"] == {"size": 13, "matched": 1, "total": 8, "overlap": 0.125}
    assert row["train_matches"] == [{"source": "train", "index": 0, "id": None}]
    assert result.targets[0]["contaminated_fraction"] == 1.0


def test_twelve_shared_tokens_are_not_a_13gram_overlap() -> None:
    eval_words = [f"e{i}" for i in range(20)]
    train_text = " ".join(eval_words[3:15])  # 12 tokens
    result = _check([train_text], [" ".join(eval_words)])
    assert result.records == []
    assert result.targets[0]["contaminated_count"] == 0


def test_ngram_threshold_raises_the_bar() -> None:
    eval_words = [f"e{i}" for i in range(20)]
    train_text = " ".join(eval_words[3:16])  # overlap 1/8
    assert _check([train_text], [" ".join(eval_words)], ngram_threshold=0.1).records
    assert not _check([train_text], [" ".join(eval_words)], ngram_threshold=0.5).records


def _reference_overlap(train: list[str], evals: list[str], n: int) -> list[float]:
    """Brute force: fraction of each eval record's distinct n-grams seen in any train record."""
    train_grams: set[tuple[str, ...]] = set()
    for t in train:
        toks = normalize_tokens(t)
        train_grams |= {tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)}
    out = []
    for e in evals:
        toks = normalize_tokens(e)
        grams = {tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)}
        out.append(len(grams & train_grams) / len(grams))
    return out


def test_ngram_overlap_matches_brute_force_reference() -> None:
    rng = random.Random(7)
    vocab = [f"w{i}" for i in range(40)]
    train = [" ".join(rng.choices(vocab, k=rng.randint(30, 80))) for _ in range(40)]
    evals = []
    for _ in range(30):
        words = rng.choices(vocab, k=rng.randint(20, 40))
        if rng.random() < 0.5:  # splice a copied span from training data
            src = normalize_tokens(rng.choice(train))
            start = rng.randint(0, len(src) - 15)
            pos = rng.randint(0, len(words))
            words[pos:pos] = src[start : start + 15]
        evals.append(" ".join(words))

    n = 5  # small n so random overlaps occur too
    expected = _reference_overlap(train, evals, n)
    result = _check(train, evals, ngram_size=n, min_ngram_size=n)
    got = {r["index"]: r["ngram"]["overlap"] for r in result.records}
    for i, exp in enumerate(expected):
        assert got.get(i, 0.0) == pytest.approx(exp, abs=1e-6)
    assert result.targets[0]["contaminated_count"] == sum(1 for e in expected if e > 0)


def test_short_record_matched_as_a_whole_and_very_short_unchecked() -> None:
    nine = "one two three four five six seven eight nine"
    result = _check(
        ["intro " + nine + " outro", "yes no"],
        [nine, "yes no", "not present at all"],
    )
    by_index = {r["index"]: r for r in result.records}
    assert by_index[0]["methods"] == ["ngram"]
    assert by_index[0]["ngram"]["size"] == 9
    # "yes no" is too short for n-grams, but exact matching still catches it.
    assert by_index[1]["methods"] == ["exact"]
    assert 2 not in by_index
    assert result.targets[0]["ngram_unchecked_count"] == 2  # "yes no" and "not present at all"


def test_exact_method_survives_case_and_punctuation() -> None:
    result = _check(["Q: What is 2 + 2? A: 4."], ["q what is 2+2 a 4"], methods=["exact"])
    assert [r["methods"] for r in result.records] == [["exact"]]


# --- MinHash ------------------------------------------------------------------


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(_ngrams(a)), set(_ngrams(b))
    return len(sa & sb) / len(sa | sb)


def test_minhash_flags_light_edits_and_estimate_tracks_exact_jaccard() -> None:
    base = (
        "Natalia sold clips to 48 of her friends in April, and then she sold half as "
        "many clips in May. How many clips did Natalia sell altogether in April and May?"
    )
    edited = base.replace("48", "46").replace("altogether", "in total")
    result = _check([edited], [base], methods=["minhash"], minhash_threshold=0.7)
    (row,) = result.records
    j = _jaccard(base, edited)
    k = 128
    assert row["minhash_similarity"] == pytest.approx(j, abs=4 * (j * (1 - j) / k) ** 0.5 + 1e-9)
    assert row["methods"] == ["minhash"]


def test_minhash_lsh_matches_exhaustive_pairs() -> None:
    """Cross-set LSH must not miss a pair whose estimate reaches the threshold."""
    from toolkit_mmqa.text_dedup import MinHasher

    rng = random.Random(3)
    alphabet = "abcdefghij "
    base = ["".join(rng.choices(alphabet, k=120)) for _ in range(12)]
    train = []
    for b in base:
        chars = list(b)
        for _ in range(rng.randint(0, 25)):
            chars[rng.randrange(len(chars))] = rng.choice(alphabet)
        train.append("".join(chars))
    threshold = 0.8
    hasher = MinHasher(num_perm=128)
    expected = set()
    for i, e in enumerate(base):
        se = hasher.signature(e)
        if any(hasher.similarity(se, hasher.signature(t)) >= threshold for t in train):
            expected.add(i)
    result = _check(train, base, methods=["minhash"], minhash_threshold=threshold)
    assert {r["index"] for r in result.records} == expected
    assert expected  # the test data does exercise near-duplicates


def test_invalid_parameters_raise() -> None:
    with pytest.raises(ValueError):
        _check(["a"], ["a"], methods=["bogus"])
    with pytest.raises(ValueError):
        _check(["a"], ["a"], ngram_size=5, min_ngram_size=6)
    with pytest.raises(ValueError):
        _check(["a"], ["a"], ngram_threshold=1.5)


# --- CLI ----------------------------------------------------------------------


QUESTION = (
    "A robe takes 2 bolts of blue fiber and half that much white fiber. "
    "How many bolts in total does it take?"
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _splits(tmp_path: Path) -> tuple[Path, Path]:
    train = _write_jsonl(
        tmp_path / "train.jsonl",
        [
            {"question": "Unrelated training question number one about apples and pears?"},
            {"question": "Copied: " + QUESTION + " Show your work."},
        ],
    )
    test = _write_jsonl(
        tmp_path / "test.jsonl",
        [
            {"id": "t0", "question": QUESTION},
            {"id": "t1", "question": "A clean evaluation question that is not in training."},
        ],
    )
    return train, test


def test_cli_contamination_fails_gate_and_reports_records(tmp_path: Path) -> None:
    train, test = _splits(tmp_path)
    out = tmp_path / "contam.json"
    code = main(
        [
            "contamination",
            "--train",
            str(train),
            "--eval",
            f"test={test}",
            "--field",
            "question",
            "--id-field",
            "id",
            "--out",
            str(out),
        ]
    )
    assert code == 1
    report = json.loads(out.read_bytes())
    pred = report["predicate"]
    assert pred["kind"] == "mmqa.contamination"
    assert pred["verdict"] == "fail" and pred["exit_code"] == 1
    assert pred["summary"]["contaminated_fraction"] == {"test": 0.5}
    assert pred["summary"]["failed_targets"] == ["test"]
    assert report["subject"][0]["name"] == "test"
    assert pred["inputs"][0]["name"] == "train.jsonl"
    (row,) = pred["details"]["contaminated_records"]
    assert row["id"] == "t0" and row["index"] == 0
    assert row["methods"] == ["ngram"]
    assert row["train_matches"] == [{"source": "train.jsonl", "index": 1, "id": None}]


def test_cli_contamination_passes_under_limit(tmp_path: Path) -> None:
    train, test = _splits(tmp_path)
    out = tmp_path / "c.json"
    code = main(
        [
            "contamination",
            "--train",
            str(train),
            "--benchmark",
            str(test),
            "--field",
            "question",
            "--max-contamination",
            "0.5",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    report = json.loads(out.read_bytes())
    assert report["predicate"]["verdict"] == "pass"
    assert report["predicate"]["details"]["targets"][0]["role"] == "benchmark"


def test_cli_contamination_malformed_input_writes_error_report(tmp_path: Path) -> None:
    train, _ = _splits(tmp_path)
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"question": "ok"}\n{not json\n', encoding="utf-8")
    out = tmp_path / "c.json"
    code = main(
        ["contamination", "--train", str(train), "--eval", str(bad), "--field", "question"]
        + ["--out", str(out)]
    )
    assert code == 2
    report = json.loads(out.read_bytes())
    assert report["predicate"]["verdict"] == "error"
    assert report["predicate"]["exit_code"] == 2
    assert "bad.jsonl:2" in report["predicate"]["details"]["error"]


def test_cli_contamination_missing_field_is_an_error(tmp_path: Path) -> None:
    train, test = _splits(tmp_path)
    code = main(["contamination", "--train", str(train), "--eval", str(test)])
    assert code == 2  # records have no "text" field


def test_cli_contamination_needs_a_target(tmp_path: Path) -> None:
    train, _ = _splits(tmp_path)
    assert main(["contamination", "--train", str(train)]) == 2


def test_cli_contamination_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    train, test = _splits(tmp_path)
    code = main(
        ["contamination", "--train", str(train), "--eval", str(test), "--field", "question"]
        + ["--format", "markdown"]
    )
    assert code == 1
    text = capsys.readouterr().out
    assert "| test.jsonl | 2 | 1 | 0.5000 |" in text


def test_cli_contamination_report_validates_against_schema(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "report-envelope.v1.json").read_text(
            encoding="utf-8"
        )
    )
    train, test = _splits(tmp_path)
    out = tmp_path / "c.json"
    main(
        ["contamination", "--train", str(train), "--eval", str(test), "--field", "question"]
        + ["--methods", "exact,ngram,minhash", "--out", str(out)]
    )
    jsonschema.Draft202012Validator(schema).validate(json.loads(out.read_bytes()))
