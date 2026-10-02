"""Record-level deduplication for text datasets (JSONL, JSON, CSV, text).

Two records are *exact duplicates* when their normalized texts are equal
(Unicode NFKC, lowercase, ``\\w+`` tokens joined by single spaces; the same
normalization as the contamination check). Two records are *near-duplicates*
when the MinHash estimate of the Jaccard similarity of their character-trigram
sets is at least the threshold (see :mod:`toolkit_mmqa.text_dedup`).

Duplicates are grouped transitively. The record kept from each group is the
first one in input order; every other member is *removable*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .contamination import normalize_tokens
from .records import Record
from .text_dedup import find_near_duplicates


@dataclass(frozen=True)
class SourceRecords:
    """Records read from one input file."""

    name: str
    records: Sequence[Record]


@dataclass
class DedupResult:
    """Outcome of :func:`dedup_records`.

    Attributes:
        record_count: Records read across all sources.
        exact_groups: Groups (2+ members) of exact duplicates, as record refs
            ``{"source", "index", "id"}``, in input order.
        near_groups: Groups of near-duplicates (only when requested). Exact
            duplicates are also near-duplicates of each other.
        near_pairs: Verified near-duplicate pairs with their similarity.
        removable: Refs of records dropped when one record per group is kept.
        empty_count: Records whose text has no word characters (not deduplicated).
    """

    record_count: int
    exact_groups: list[list[dict[str, Any]]]
    near_groups: list[list[dict[str, Any]]] | None
    near_pairs: list[dict[str, Any]] | None
    removable: list[dict[str, Any]]
    empty_count: int

    @property
    def exact_duplicate_count(self) -> int:
        """Records removable by exact deduplication alone."""
        return sum(len(g) - 1 for g in self.exact_groups)


def _ref(source: str, rec: Record) -> dict[str, Any]:
    return {"source": source, "index": rec.index, "id": rec.id}


def dedup_records(
    sources: Sequence[SourceRecords],
    *,
    near_duplicates: bool = False,
    threshold: float = 0.8,
    num_perm: int = 128,
) -> DedupResult:
    """Find exact and (optionally) near-duplicate records across *sources*.

    Raises:
        ValueError: If the threshold is outside [0, 1].
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")

    order: list[tuple[str, Record]] = [(s.name, r) for s in sources for r in s.records]
    keys = [f"{i:012d}" for i in range(len(order))]  # position keys keep input order

    by_text: dict[str, list[int]] = {}
    empty = 0
    for pos, (_, rec) in enumerate(order):
        tokens = normalize_tokens(rec.text)
        if not tokens:
            empty += 1
            continue
        by_text.setdefault(" ".join(tokens), []).append(pos)
    exact_pos = [g for g in by_text.values() if len(g) > 1]
    exact_pos.sort(key=lambda g: g[0])

    # Union-find over positions: exact groups, then near-duplicate pairs.
    parent = list(range(len(order)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for g in exact_pos:
        for p in g[1:]:
            union(g[0], p)

    near_groups = None
    near_pairs = None
    if near_duplicates:
        texts = {keys[p]: rec.text for p, (_, rec) in enumerate(order) if rec.text.strip()}
        nd = find_near_duplicates(texts, threshold=threshold, num_perm=num_perm)
        near_pairs = []
        for pair, sim in sorted(nd.similarity_scores.items()):
            a, b = (int(k) for k in pair.split("|"))
            union(a, b)
            near_pairs.append({"a": _ref(*order[a]), "b": _ref(*order[b]), "similarity": sim})
        near_groups = [[_ref(*order[int(k)]) for k in sorted(g)] for g in nd.near_duplicate_groups]
        near_groups.sort(key=lambda g: (g[0]["source"], g[0]["index"]))

    removable = [_ref(*order[p]) for p in range(len(order)) if find(p) != p]
    return DedupResult(
        record_count=len(order),
        exact_groups=[[_ref(*order[p]) for p in g] for g in exact_pos],
        near_groups=near_groups,
        near_pairs=near_pairs,
        removable=removable,
        empty_count=empty,
    )
