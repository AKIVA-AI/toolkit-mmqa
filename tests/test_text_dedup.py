"""Tests for text-level deduplication (MinHash)."""

from __future__ import annotations

import pytest

from toolkit_mmqa.text_dedup import (
    MinHasher,
    MinHashSignature,
    TextDedupResult,
    _band_candidates,
    _choose_bands,
    _ngrams,
    find_near_duplicates,
)

# ============================================================================
# N-gram extraction
# ============================================================================


def test_ngrams_basic() -> None:
    """Basic trigram extraction."""
    result = _ngrams("hello", 3)
    assert result == ["hel", "ell", "llo"]


def test_ngrams_short_text() -> None:
    """Text shorter than n returns the text itself."""
    assert _ngrams("ab", 3) == ["ab"]


def test_ngrams_empty() -> None:
    """Empty text returns empty list."""
    assert _ngrams("", 3) == []


def test_ngrams_whitespace_only() -> None:
    """Whitespace-only text returns empty list after strip."""
    assert _ngrams("   ", 3) == []


def test_ngrams_case_insensitive() -> None:
    """N-grams are lowercased."""
    result = _ngrams("ABC", 2)
    assert all(g == g.lower() for g in result)


# ============================================================================
# MinHasher
# ============================================================================


def test_minhash_identical_texts() -> None:
    """Identical texts produce identical signatures."""
    hasher = MinHasher(num_perm=64)
    sig1 = hasher.signature("The quick brown fox jumps over the lazy dog")
    sig2 = hasher.signature("The quick brown fox jumps over the lazy dog")
    assert sig1 == sig2
    assert hasher.similarity(sig1, sig2) == 1.0


def test_minhash_similar_texts() -> None:
    """Similar texts produce high similarity."""
    hasher = MinHasher(num_perm=128)
    sig1 = hasher.signature("The quick brown fox jumps over the lazy dog")
    sig2 = hasher.signature("The quick brown fox jumps over the lazy cat")
    sim = hasher.similarity(sig1, sig2)
    assert sim > 0.5  # High overlap


def test_minhash_different_texts() -> None:
    """Completely different texts produce low similarity."""
    hasher = MinHasher(num_perm=128)
    sig1 = hasher.signature("aaaaaaaaaaaaaaaaaaa")
    sig2 = hasher.signature("zzzzzzzzzzzzzzzzzzz")
    sim = hasher.similarity(sig1, sig2)
    assert sim < 0.3


def test_minhash_empty_text() -> None:
    """Empty text gets a default signature."""
    hasher = MinHasher(num_perm=32)
    sig = hasher.signature("")
    assert len(sig.values) == 32


def test_minhash_signature_length() -> None:
    """Signature has correct number of permutations."""
    hasher = MinHasher(num_perm=64)
    sig = hasher.signature("test text")
    assert sig.num_perm == 64


def test_minhash_different_perm_error() -> None:
    """Comparing signatures with different num_perm raises error."""
    h1 = MinHasher(num_perm=32)
    h2 = MinHasher(num_perm=64)
    sig1 = h1.signature("text")
    sig2 = h2.signature("text")
    with pytest.raises(ValueError, match="same number of permutations"):
        h1.similarity(sig1, sig2)


def test_minhash_deterministic() -> None:
    """Same seed produces same results."""
    h1 = MinHasher(num_perm=64, seed=42)
    h2 = MinHasher(num_perm=64, seed=42)
    sig1 = h1.signature("test")
    sig2 = h2.signature("test")
    assert sig1 == sig2


def test_minhash_different_seeds() -> None:
    """Different seeds produce different signatures."""
    h1 = MinHasher(num_perm=64, seed=1)
    h2 = MinHasher(num_perm=64, seed=2)
    sig1 = h1.signature("test")
    sig2 = h2.signature("test")
    assert sig1 != sig2


# ============================================================================
# find_near_duplicates
# ============================================================================


def test_find_near_duplicates_identical() -> None:
    """Identical texts are grouped as near-duplicates."""
    texts = {
        "file1.txt": "This is an important document about AI.",
        "file2.txt": "This is an important document about AI.",
        "file3.txt": "Something completely different here.",
    }
    result = find_near_duplicates(texts, threshold=0.8)
    assert len(result.near_duplicate_groups) == 1
    assert sorted(result.near_duplicate_groups[0]) == ["file1.txt", "file2.txt"]


def test_find_near_duplicates_similar() -> None:
    """Similar texts are grouped when threshold is met."""
    texts = {
        "a.txt": "The quick brown fox jumps over the lazy dog in the park",
        "b.txt": "The quick brown fox jumps over the lazy cat in the park",
        "c.txt": "Completely unrelated content about quantum physics",
    }
    result = find_near_duplicates(texts, threshold=0.5, num_perm=256)
    assert len(result.near_duplicate_groups) >= 1
    # a.txt and b.txt should be grouped
    for group in result.near_duplicate_groups:
        if "a.txt" in group:
            assert "b.txt" in group
            break
    else:
        pytest.fail("Expected a.txt and b.txt to be in the same group")


def test_find_near_duplicates_no_duplicates() -> None:
    """Distinct texts produce no groups."""
    texts = {
        "a.txt": "aaaaaaaaaaaaaaaaa",
        "b.txt": "zzzzzzzzzzzzzzzzz",
    }
    result = find_near_duplicates(texts, threshold=0.9)
    assert len(result.near_duplicate_groups) == 0


def test_find_near_duplicates_empty_input() -> None:
    """Empty input produces empty result."""
    result = find_near_duplicates({})
    assert result.near_duplicate_groups == []
    assert result.similarity_scores == {}


def test_find_near_duplicates_invalid_threshold() -> None:
    """Invalid threshold raises ValueError."""
    with pytest.raises(ValueError, match="Threshold must be"):
        find_near_duplicates({}, threshold=1.5)
    with pytest.raises(ValueError, match="Threshold must be"):
        find_near_duplicates({}, threshold=-0.1)


def test_find_near_duplicates_lsh_matches_exhaustive() -> None:
    """LSH banding produces the same duplicate groups as exhaustive all-pairs.

    Regression guard for the banding optimization: correctness must not change
    when LSH filtering is enabled, only the number of comparisons.
    """
    base = "the quick brown fox jumps over the lazy dog " * 20
    texts: dict[str, str] = {
        # A known near-duplicate cluster (tiny edits share high Jaccard).
        "dup_a.txt": base,
        "dup_b.txt": base + "tail",
        "dup_c.txt": base.replace("lazy", "sleepy", 1),
    }
    # Many unique documents so banding actually has something to filter.
    for i in range(60):
        texts[f"unique_{i}.txt"] = f"completely distinct content number {i} " + ("x" * (i % 7))

    lsh = find_near_duplicates(texts, threshold=0.7, num_perm=128, use_lsh=True)
    exhaustive = find_near_duplicates(texts, threshold=0.7, num_perm=128, use_lsh=False)

    assert sorted(map(sorted, lsh.near_duplicate_groups)) == sorted(
        map(sorted, exhaustive.near_duplicate_groups)
    )
    # The known cluster must survive banding.
    assert { "dup_a.txt", "dup_b.txt" } <= {
        p for g in lsh.near_duplicate_groups for p in g
    }


def _near_threshold_corpus() -> dict[str, str]:
    """30 document pairs whose MinHash similarity sits just above 0.8."""
    import random

    rng = random.Random(7)
    vocab = [f"w{i}" for i in range(5000)]
    texts: dict[str, str] = {}
    for k in range(30):
        words = [rng.choice(vocab) for _ in range(200)]
        texts[f"doc{k:02d}_a.txt"] = " ".join(words)
        variant = list(words)
        for idx in rng.sample(range(200), 28):
            variant[idx] = rng.choice(vocab)
        texts[f"doc{k:02d}_b.txt"] = " ".join(variant)
    return texts


def test_lsh_recall_for_pairs_just_above_threshold() -> None:
    """LSH must not drop pairs whose similarity is only slightly above the threshold.

    Regression: the old band choice (8 bands x 16 rows at t=0.8) put the S-curve
    midpoint near the threshold and found only ~20-45% of these pairs.
    """
    texts = _near_threshold_corpus()
    exhaustive = find_near_duplicates(texts, threshold=0.8, use_lsh=False)
    lsh = find_near_duplicates(texts, threshold=0.8, use_lsh=True)

    near = [s for s in exhaustive.similarity_scores.values() if s < 0.85]
    assert len(near) >= 5, "fixture must contain pairs just above the threshold"
    assert lsh.near_duplicate_groups == exhaustive.near_duplicate_groups
    assert lsh.similarity_scores == exhaustive.similarity_scores


@pytest.mark.parametrize("num_perm", [16, 64, 100, 128, 256])
@pytest.mark.parametrize("threshold", [0.05, 0.3, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0])
def test_choose_bands_guarantees_candidate_for_every_passing_pair(
    num_perm: int, threshold: float
) -> None:
    """More bands than the mismatches a passing pair can have => no missed pairs.

    A pair passes verification with up to ``max_mismatch`` differing signature
    slots. Each mismatch can spoil at most one band, so ``bands > max_mismatch``
    guarantees at least one fully matching band (pigeonhole).
    """
    bands, rows = _choose_bands(num_perm, threshold)
    assert bands >= 1 and rows >= 1
    assert bands * rows <= num_perm
    max_mismatch = max(m for m in range(num_perm + 1) if (num_perm - m) / num_perm >= threshold)
    assert bands > max_mismatch


def test_band_candidates_catches_spread_mismatches_at_threshold() -> None:
    """Two signatures at similarity 103/128 (>= 0.8) with evenly spread mismatches."""
    base = tuple(range(128))
    spread = tuple(-1 if i % 5 == 0 and i < 125 else v for i, v in enumerate(base))
    mismatches = sum(a != b for a, b in zip(base, spread, strict=True))
    assert mismatches == 25
    sigs = {
        "a": MinHashSignature(values=base),
        "b": MinHashSignature(values=spread),
        "c": MinHashSignature(values=tuple(v + 1000 for v in base)),
    }
    assert ("a", "b") in _band_candidates(sigs, 128, 0.8)


def test_text_dedup_result_to_json() -> None:
    """TextDedupResult serializes correctly."""
    result = TextDedupResult(
        near_duplicate_groups=[["a.txt", "b.txt"]],
        similarity_scores={"a.txt|b.txt": 0.95},
    )
    j = result.to_json()
    assert j["near_duplicate_groups"] == [["a.txt", "b.txt"]]
    assert j["similarity_scores"]["a.txt|b.txt"] == 0.95


# ============================================================================
# Vectorized (NumPy) MinHash
# ============================================================================


def _random_texts(n: int, seed: int) -> list[str]:
    import random

    rng = random.Random(seed)
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
    return [" ".join(rng.choices(words, k=rng.randint(1, 300))) for _ in range(n)]


def test_numpy_signatures_equal_pure_python() -> None:
    """The vectorized path must give bit-identical signatures."""
    pytest.importorskip("numpy")
    fast = MinHasher(num_perm=64, use_numpy=True)
    slow = MinHasher(num_perm=64, use_numpy=False)
    assert fast.vectorized and not slow.vectorized
    for text in _random_texts(40, seed=1) + ["", "ab", "x" * 5000]:
        assert fast.signature(text) == slow.signature(text)


def test_minhash_estimate_within_standard_error_of_exact_jaccard() -> None:
    """Broder (1997): each slot agrees with probability J, so the estimate has
    standard error sqrt(J(1-J)/k) (Leskovec, Rajaraman, Ullman, Mining of Massive
    Datasets, section 3.3). Check the estimate is within 4 standard errors."""
    from toolkit_mmqa.text_dedup import _ngrams

    k = 256
    hasher = MinHasher(num_perm=k, use_numpy=False)
    texts = _random_texts(20, seed=2)
    checked = 0
    for a, b in zip(texts, texts[1:], strict=False):
        sa, sb = set(_ngrams(a)), set(_ngrams(b))
        j = len(sa & sb) / len(sa | sb)
        est = hasher.similarity(hasher.signature(a), hasher.signature(b))
        assert abs(est - j) <= 4 * (j * (1 - j) / k) ** 0.5 + 1e-9, (est, j)
        checked += 1
    assert checked == 19
