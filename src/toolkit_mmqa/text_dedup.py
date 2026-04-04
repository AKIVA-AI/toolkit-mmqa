"""Near-duplicate text detection using MinHash with Jaccard similarity.

Provides text-level deduplication beyond exact hash matching by detecting
near-duplicate documents using the MinHash locality-sensitive hashing
technique.

**Algorithm overview**

1. Each document is **shingled** into overlapping character n-grams
   (default trigrams).
2. A family of ``num_perm`` random hash functions of the form
   ``h(x) = (a*x + b) mod p`` (where *p* is a large Mersenne prime)
   is applied to every shingle hash.
3. For each hash function the **minimum** value across all shingles is
   kept, producing a compact *MinHash signature*.
4. The **Jaccard similarity** of two documents is estimated as the
   fraction of signature slots that agree.
5. Documents whose estimated Jaccard similarity meets or exceeds
   ``threshold`` are grouped via **Union-Find** (with path compression).

References:
    Broder, A. Z. (1997). *On the resemblance and containment of
    documents*. In Proc. Compression and Complexity of Sequences.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

# Large Mersenne prime used as the modulus in the universal hash family.
# 2^61 - 1 is prime and large enough to avoid collision issues with
# 32-bit token hashes while fitting in a 64-bit integer.
_MERSENNE_PRIME = (1 << 61) - 1

# Sentinel value used for empty-document signatures (maximum 32-bit value).
_MAX_HASH = (1 << 32) - 1


def _ngrams(text: str, n: int = 3) -> list[str]:
    """Extract character n-grams from text.

    Args:
        text: Input text to tokenize.
        n: Size of each n-gram (default 3).

    Returns:
        List of n-gram strings.
    """
    text = text.lower().strip()
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def _hash_token(token: str) -> int:
    """Hash a token string to a 32-bit unsigned integer.

    Uses the first 4 bytes of an MD5 digest (explicitly marked as
    non-security-critical) interpreted as a little-endian uint32.
    MD5 is chosen for speed; collision resistance is not required
    because MinHash is probabilistic by design.

    Args:
        token: The n-gram string to hash.

    Returns:
        A 32-bit unsigned integer hash value.
    """
    return struct.unpack(
        "<I",
        hashlib.md5(token.encode("utf-8"), usedforsecurity=False).digest()[:4],
    )[0]


@dataclass(frozen=True)
class MinHashSignature:
    """A MinHash signature representing a document."""

    values: tuple[int, ...]

    @property
    def num_perm(self) -> int:
        return len(self.values)


class MinHasher:
    """MinHash generator for near-duplicate text detection.

    Uses random hash functions to produce compact signatures that can
    estimate Jaccard similarity between document shingle sets.

    Args:
        num_perm: Number of hash permutations (higher = more accurate, slower).
        ngram_size: Character n-gram size for shingling.
        seed: Random seed for reproducibility.
    """

    def __init__(
        self,
        num_perm: int = 128,
        ngram_size: int = 3,
        seed: int = 42,
    ) -> None:
        if num_perm < 1:
            raise ValueError(f"num_perm must be >= 1, got {num_perm}")
        if ngram_size < 1:
            raise ValueError(f"ngram_size must be >= 1, got {ngram_size}")
        self.num_perm = num_perm
        self.ngram_size = ngram_size
        # Generate random hash function coefficients for the universal hash
        # family: h_i(x) = (a_i * x + b_i) mod p, where p is a Mersenne prime.
        # Each coefficient pair defines one independent hash function.
        import random

        rng = random.Random(seed)  # nosec B311 - not used for security
        self._a = tuple(rng.randint(1, _MERSENNE_PRIME - 1) for _ in range(num_perm))
        self._b = tuple(rng.randint(0, _MERSENNE_PRIME - 1) for _ in range(num_perm))

    def signature(self, text: str) -> MinHashSignature:
        """Compute the MinHash signature for a text document.

        Args:
            text: The document text.

        Returns:
            MinHashSignature with `num_perm` hash values.
        """
        tokens = _ngrams(text, self.ngram_size)
        if not tokens:
            return MinHashSignature(values=tuple(_MAX_HASH for _ in range(self.num_perm)))

        token_hashes = [_hash_token(t) for t in set(tokens)]

        min_vals: list[int] = []
        for i in range(self.num_perm):
            a, b = self._a[i], self._b[i]
            min_h = min((a * h + b) % _MERSENNE_PRIME for h in token_hashes)
            min_vals.append(min_h)

        return MinHashSignature(values=tuple(min_vals))

    def similarity(self, sig_a: MinHashSignature, sig_b: MinHashSignature) -> float:
        """Estimate Jaccard similarity between two signatures.

        Args:
            sig_a: First document signature.
            sig_b: Second document signature.

        Returns:
            Estimated Jaccard similarity in [0.0, 1.0].
        """
        if sig_a.num_perm != sig_b.num_perm:
            raise ValueError("Signatures must have the same number of permutations")
        matches = sum(a == b for a, b in zip(sig_a.values, sig_b.values, strict=True))
        return matches / sig_a.num_perm


@dataclass
class TextDedupResult:
    """Result of near-duplicate text detection."""

    near_duplicate_groups: list[list[str]] = field(default_factory=list)
    similarity_scores: dict[str, float] = field(default_factory=dict)

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "near_duplicate_groups": self.near_duplicate_groups,
            "similarity_scores": self.similarity_scores,
        }


def find_near_duplicates(
    file_texts: dict[str, str],
    *,
    threshold: float = 0.8,
    num_perm: int = 128,
    ngram_size: int = 3,
) -> TextDedupResult:
    """Find near-duplicate text files using MinHash.

    Args:
        file_texts: Mapping of file path to file text content.
        threshold: Jaccard similarity threshold for near-duplicate detection.
        num_perm: Number of hash permutations.
        ngram_size: Character n-gram size.

    Returns:
        TextDedupResult with groups of near-duplicate files.
    """
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("Threshold must be between 0.0 and 1.0")
    if num_perm < 1:
        raise ValueError(f"num_perm must be >= 1, got {num_perm}")
    if ngram_size < 1:
        raise ValueError(f"ngram_size must be >= 1, got {ngram_size}")

    hasher = MinHasher(num_perm=num_perm, ngram_size=ngram_size)
    signatures: dict[str, MinHashSignature] = {}

    for path, text in file_texts.items():
        signatures[path] = hasher.signature(text)

    paths = list(signatures.keys())

    # --- Union-Find (disjoint-set) data structure ---
    # Each document starts as its own set.  When two documents exceed the
    # similarity threshold they are merged.  Path compression (the
    # grandparent trick in `find`) keeps amortised cost near O(1).
    parent: dict[str, str] = {p: p for p in paths}

    def find(x: str) -> str:
        """Find root with path-compression (halving)."""
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        """Merge the sets containing *x* and *y*."""
        parent[find(x)] = find(y)

    # --- Pairwise comparison ---
    # O(n^2) comparisons; acceptable for typical dataset sizes.
    scores: dict[str, float] = {}
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            sim = hasher.similarity(signatures[paths[i]], signatures[paths[j]])
            pair_key = f"{paths[i]}|{paths[j]}"
            if sim >= threshold:
                scores[pair_key] = round(sim, 4)
                union(paths[i], paths[j])

    # --- Collect connected components ---
    groups_map: dict[str, list[str]] = {}
    for p in paths:
        root = find(p)
        groups_map.setdefault(root, []).append(p)

    # Only keep groups with 2+ members (actual near-duplicates).
    groups = [sorted(g) for g in groups_map.values() if len(g) > 1]
    # Sort: largest groups first, then alphabetically for determinism.
    groups.sort(key=lambda g: (-len(g), g[0]))

    return TextDedupResult(near_duplicate_groups=groups, similarity_scores=scores)
