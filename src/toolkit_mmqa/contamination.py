"""Train/eval contamination: which evaluation records also appear in training data.

An evaluation (or benchmark) record is *contaminated* when at least one enabled
method matches it against any training record:

``exact``
    The normalized texts are equal. Normalization: Unicode NFKC, lowercase,
    keep only word characters (``\\w+`` tokens) joined by single spaces. So
    case, punctuation and whitespace differences do not hide a copy.

``ngram``
    The record shares word n-grams with the training data. Following the GPT-3
    contamination study (Brown et al. 2020, "Language Models are Few-Shot
    Learners", Appendix C), the default is 13-grams over normalized tokens and a
    record is flagged when *any* of its n-grams occurs in a training record
    (``ngram_threshold=0``). ``overlap`` is the fraction of the record's
    distinct n-grams found in training data; raise ``ngram_threshold`` to
    flag only records with at least that fraction. A record with fewer tokens
    than ``ngram_size`` but at least ``min_ngram_size`` is flagged when its
    whole token sequence occurs contiguously in a training record. Shorter
    records are checked by ``exact`` only and counted as ``ngram_unchecked``.

``minhash``
    Estimated Jaccard similarity of character-trigram sets (MinHash, Broder
    1997) is at least ``minhash_threshold``. Catches light paraphrase and edits.
    LSH bands are chosen so no pair at or above the threshold is missed (see
    :func:`toolkit_mmqa.text_dedup._choose_bands`).

The evaluation side is indexed in memory and training records are streamed, so
memory grows with the evaluation set, not the training set.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .records import Record
from .text_dedup import MinHasher, MinHashSignature, _choose_bands

METHODS = ("exact", "ngram", "minhash")
DEFAULT_METHODS = ("exact", "ngram")
DEFAULT_NGRAM_SIZE = 13
DEFAULT_MIN_NGRAM_SIZE = 8
DEFAULT_MINHASH_THRESHOLD = 0.8
PREVIEW_CHARS = 160

_TOKEN_RE = re.compile(r"\w+")


def normalize_tokens(text: str) -> list[str]:
    """Tokens used by the exact and n-gram methods (NFKC, lowercase, ``\\w+``)."""
    return _TOKEN_RE.findall(unicodedata.normalize("NFKC", text).lower())


def record_ngrams(
    tokens: Sequence[str], ngram_size: int, min_ngram_size: int
) -> tuple[set[tuple[str, ...]], int | None]:
    """Distinct n-grams of an evaluation record and the gram length used.

    Returns ``(grams, length)``. ``length`` is ``ngram_size`` for long records,
    the record length for records between ``min_ngram_size`` and
    ``ngram_size - 1`` tokens (one gram: the whole record), and ``None`` for
    shorter records, which the n-gram method does not check.
    """
    n = len(tokens)
    if n >= ngram_size:
        return {tuple(tokens[i : i + ngram_size]) for i in range(n - ngram_size + 1)}, ngram_size
    if n >= min_ngram_size:
        return {tuple(tokens)}, n
    return set(), None


@dataclass(frozen=True)
class Target:
    """An evaluation split or benchmark checked against the training data."""

    name: str
    records: Sequence[Record]
    role: str = "eval"


@dataclass
class _State:
    target: int
    record: Record
    exact_key: str | None
    grams: set[tuple[str, ...]]
    gram_len: int | None
    signature: MinHashSignature | None = None
    matched: set[tuple[str, ...]] = field(default_factory=set)
    exact_hit: bool = False
    minhash_best: float = 0.0
    train_matches: list[dict[str, Any]] = field(default_factory=list)
    train_match_count: int = 0


@dataclass
class ContaminationResult:
    """Outcome of :func:`check_contamination`.

    Attributes:
        targets: One summary dict per target (record and contamination counts).
        records: One dict per contaminated record, ordered by target then index.
        train_record_count: Training records read, per source name.
        parameters: The settings used.
    """

    targets: list[dict[str, Any]]
    records: list[dict[str, Any]]
    train_record_count: dict[str, int]
    parameters: dict[str, Any]

    def failed_targets(self, max_contamination: float) -> list[str]:
        """Names of targets whose contaminated fraction exceeds the limit."""
        return [t["name"] for t in self.targets if t["contaminated_fraction"] > max_contamination]


def check_contamination(
    train_sources: Iterable[tuple[str, Iterable[Record]]],
    targets: Sequence[Target],
    *,
    methods: Sequence[str] = DEFAULT_METHODS,
    ngram_size: int = DEFAULT_NGRAM_SIZE,
    min_ngram_size: int = DEFAULT_MIN_NGRAM_SIZE,
    ngram_threshold: float = 0.0,
    minhash_threshold: float = DEFAULT_MINHASH_THRESHOLD,
    num_perm: int = 128,
    max_train_matches: int = 5,
) -> ContaminationResult:
    """Find evaluation records that also occur in the training data.

    Args:
        train_sources: ``(name, records)`` pairs; records are streamed once.
        targets: Evaluation splits or benchmarks to check.
        methods: Any of ``exact``, ``ngram``, ``minhash``.
        ngram_size: Word n-gram length (default 13).
        min_ngram_size: Shortest record checked by the n-gram method.
        ngram_threshold: Minimum overlap fraction to flag; ``0`` flags any overlap.
        minhash_threshold: Minimum estimated Jaccard similarity to flag.
        num_perm: MinHash permutations.
        max_train_matches: Training records listed per contaminated record.

    Raises:
        ValueError: On an unknown method or out-of-range parameter.
    """
    methods = tuple(dict.fromkeys(methods))
    unknown = sorted(set(methods) - set(METHODS))
    if unknown or not methods:
        raise ValueError(f"methods must be a non-empty subset of {list(METHODS)}, got {unknown}")
    if ngram_size < 1 or min_ngram_size < 1 or min_ngram_size > ngram_size:
        raise ValueError("need 1 <= min_ngram_size <= ngram_size")
    if not 0.0 <= ngram_threshold <= 1.0:
        raise ValueError(f"ngram_threshold must be in [0, 1], got {ngram_threshold}")
    if not 0.0 < minhash_threshold <= 1.0:
        raise ValueError(f"minhash_threshold must be in (0, 1], got {minhash_threshold}")

    use_exact = "exact" in methods
    use_ngram = "ngram" in methods
    use_minhash = "minhash" in methods

    hasher = MinHasher(num_perm=num_perm) if use_minhash else None
    bands, rows = _choose_bands(num_perm, minhash_threshold) if use_minhash else (0, 0)

    states: list[_State] = []
    exact_index: dict[str, list[int]] = {}
    gram_index: dict[tuple[str, ...], list[int]] = {}
    gram_lengths: set[int] = set()
    band_index: list[dict[tuple[int, ...], list[int]]] = [{} for _ in range(bands)]

    for t_idx, target in enumerate(targets):
        for rec in target.records:
            tokens = normalize_tokens(rec.text)
            key = " ".join(tokens) if tokens else None
            grams, gram_len = (
                record_ngrams(tokens, ngram_size, min_ngram_size) if use_ngram else (set(), None)
            )
            state = _State(target=t_idx, record=rec, exact_key=key, grams=grams, gram_len=gram_len)
            s_idx = len(states)
            states.append(state)
            if use_exact and key is not None:
                exact_index.setdefault(key, []).append(s_idx)
            if gram_len is not None:
                gram_lengths.add(gram_len)
                for g in grams:
                    gram_index.setdefault(g, []).append(s_idx)
            if hasher is not None and rec.text.strip():
                state.signature = hasher.signature(rec.text)
                for b in range(bands):
                    band_key = state.signature.values[b * rows : (b + 1) * rows]
                    band_index[b].setdefault(band_key, []).append(s_idx)

    sorted_lengths = sorted(gram_lengths)
    train_counts: dict[str, int] = {}

    for source_name, records in train_sources:
        count = 0
        for rec in records:
            count += 1
            hit: set[int] = set()
            tokens = normalize_tokens(rec.text)
            if use_exact and tokens:
                for s_idx in exact_index.get(" ".join(tokens), ()):
                    states[s_idx].exact_hit = True
                    hit.add(s_idx)
            if sorted_lengths:
                n_tok = len(tokens)
                for k in sorted_lengths:
                    for i in range(n_tok - k + 1):
                        g = tuple(tokens[i : i + k])
                        owners = gram_index.get(g)
                        if owners is None:
                            continue
                        for s_idx in owners:
                            states[s_idx].matched.add(g)
                            hit.add(s_idx)
            if hasher is not None and rec.text.strip():
                sig = hasher.signature(rec.text)
                candidates: set[int] = set()
                for b in range(bands):
                    candidates.update(band_index[b].get(sig.values[b * rows : (b + 1) * rows], ()))
                for s_idx in candidates:
                    other = states[s_idx].signature
                    if other is None:
                        continue
                    sim = hasher.similarity(sig, other)
                    if sim >= minhash_threshold:
                        state = states[s_idx]
                        state.minhash_best = max(state.minhash_best, sim)
                        hit.add(s_idx)
            for s_idx in hit:
                state = states[s_idx]
                state.train_match_count += 1
                if len(state.train_matches) < max_train_matches:
                    state.train_matches.append(
                        {"source": source_name, "index": rec.index, "id": rec.id}
                    )
        train_counts[source_name] = train_counts.get(source_name, 0) + count

    target_rows: list[dict[str, Any]] = []
    flagged: list[dict[str, Any]] = []
    for t_idx, target in enumerate(targets):
        mine = [s for s in states if s.target == t_idx]
        by_method = {m: 0 for m in methods}
        contaminated = 0
        unchecked = 0
        for s in mine:
            hits: list[str] = []
            overlap = len(s.matched) / len(s.grams) if s.grams else 0.0
            if use_exact and s.exact_hit:
                hits.append("exact")
            if use_ngram:
                if s.gram_len is None:
                    unchecked += 1
                elif s.matched and overlap >= ngram_threshold:
                    hits.append("ngram")
            if use_minhash and s.minhash_best >= minhash_threshold:
                hits.append("minhash")
            for m in hits:
                by_method[m] += 1
            if not hits:
                continue
            contaminated += 1
            row: dict[str, Any] = {
                "target": target.name,
                "index": s.record.index,
                "id": s.record.id,
                "methods": hits,
                "preview": s.record.text[:PREVIEW_CHARS],
                "train_match_count": s.train_match_count,
                "train_matches": s.train_matches,
            }
            if use_ngram and s.gram_len is not None:
                row["ngram"] = {
                    "size": s.gram_len,
                    "matched": len(s.matched),
                    "total": len(s.grams),
                    "overlap": round(overlap, 6),
                }
            if use_minhash:
                row["minhash_similarity"] = round(s.minhash_best, 6)
            flagged.append(row)
        n = len(mine)
        target_rows.append(
            {
                "name": target.name,
                "role": target.role,
                "record_count": n,
                "contaminated_count": contaminated,
                "contaminated_fraction": round(contaminated / n, 6) if n else 0.0,
                "by_method": by_method,
                "ngram_unchecked_count": unchecked,
            }
        )

    return ContaminationResult(
        targets=target_rows,
        records=flagged,
        train_record_count=train_counts,
        parameters={
            "methods": list(methods),
            "ngram_size": ngram_size,
            "min_ngram_size": min_ngram_size,
            "ngram_threshold": ngram_threshold,
            "minhash_threshold": minhash_threshold,
            "num_perm": num_perm,
            "normalization": "NFKC, lowercase, \\w+ tokens",
        },
    )
