"""Tests for text-level deduplication (MinHash) — Task 6."""

from __future__ import annotations

import pytest

from toolkit_mmqa.text_dedup import (
    MinHasher,
    TextDedupResult,
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


def test_text_dedup_result_to_json() -> None:
    """TextDedupResult serializes correctly."""
    result = TextDedupResult(
        near_duplicate_groups=[["a.txt", "b.txt"]],
        similarity_scores={"a.txt|b.txt": 0.95},
    )
    j = result.to_json()
    assert j["near_duplicate_groups"] == [["a.txt", "b.txt"]]
    assert j["similarity_scores"]["a.txt|b.txt"] == 0.95
