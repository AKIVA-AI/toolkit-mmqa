"""Near-duplicate text detection using MinHash with Jaccard similarity.

Provides text-level deduplication beyond exact hash matching by detecting
near-duplicate documents using the MinHash locality-sensitive hashing
technique.

**Algorithm overview**

1. Each document is **shingled** into overlapping character n-grams
   (default trigrams).
2. A family of ``num_perm`` random hash functions of the form
   ``h(x) = ((a*x + b) mod 2^64) mod p`` (*p* = 2^61 - 1, a Mersenne prime)
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
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# Large Mersenne prime used as the modulus in the universal hash family.
# 2^61 - 1 is prime and large enough to avoid collision issues with
# 32-bit token hashes while fitting in a 64-bit integer.
_MERSENNE_PRIME = (1 << 61) - 1

# Sentinel value used for empty-document signatures (maximum 32-bit value).
_MAX_HASH = (1 << 32) - 1

# h(x) = ((a*x + b) mod 2^64) mod p, with a, b drawn below p. Reducing mod 2^64
# first is what uint64 arithmetic does, so the NumPy path computes exactly the
# same values as the pure-Python path. (The same construction as datasketch.)
_MASK64 = (1 << 64) - 1

# Upper bound on a*x products held in memory at once by the NumPy path.
_NUMPY_CHUNK = 1 << 20


def _numpy():
    """Return the numpy module, or None when it is not installed."""
    try:
        import numpy
    except ImportError:
        return None
    return numpy


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
        use_numpy: Vectorize with NumPy when it is installed (the ``[fast]``
            extra). ``None`` (default) uses NumPy if available. Both paths give
            identical signatures.
    """

    def __init__(
        self,
        num_perm: int = 128,
        ngram_size: int = 3,
        seed: int = 42,
        use_numpy: bool | None = None,
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
        np = _numpy() if use_numpy is not False else None
        if use_numpy and np is None:
            raise RuntimeError("use_numpy=True needs numpy: pip install '...[fast]'")
        self._np = np
        if np is not None:
            self._a_np = np.array(self._a, dtype=np.uint64).reshape(-1, 1)
            self._b_np = np.array(self._b, dtype=np.uint64).reshape(-1, 1)

    @property
    def vectorized(self) -> bool:
        """True when signatures are computed with NumPy."""
        return self._np is not None

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

        np = self._np
        if np is not None:
            hv = np.array(token_hashes, dtype=np.uint64)
            prime = np.uint64(_MERSENNE_PRIME)
            step = max(1, _NUMPY_CHUNK // self.num_perm)
            mins = np.full(self.num_perm, np.iinfo(np.uint64).max, dtype=np.uint64)
            for start in range(0, len(hv), step):
                # uint64 multiply/add wrap modulo 2^64, matching _MASK64 above.
                block = (self._a_np * hv[start : start + step] + self._b_np) % prime
                mins = np.minimum(mins, block.min(axis=1))
            return MinHashSignature(values=tuple(int(v) for v in mins))

        min_vals: list[int] = []
        for i in range(self.num_perm):
            a, b = self._a[i], self._b[i]
            min_h = min(((a * h + b) & _MASK64) % _MERSENNE_PRIME for h in token_hashes)
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


def _max_mismatches(num_perm: int, threshold: float) -> int:
    """Largest number of differing signature slots a pair can have and still pass.

    Uses the same expression as the verification step (``matches / num_perm >=
    threshold``) so float rounding cannot make the two disagree.
    """
    for mismatches in range(num_perm, -1, -1):
        if (num_perm - mismatches) / num_perm >= threshold:
            return mismatches
    return -1  # unreachable for threshold <= 1.0


def _choose_bands(num_perm: int, threshold: float) -> tuple[int, int]:
    """Pick (bands, rows) so LSH never misses a pair that verification would accept.

    A pair passes verification when at most ``m = _max_mismatches(...)``
    signature slots differ. Each differing slot can spoil at most one band, so
    with ``bands > m`` at least one band of a passing pair matches exactly and
    the pair is always a candidate (pigeonhole). Among such layouts we take the
    largest ``rows`` (fewest spurious candidates). ``bands * rows`` may be less
    than ``num_perm``; the leftover slots are simply not banded.

    This puts the S-curve midpoint well below the threshold, so LSH output is
    identical to the exhaustive all-pairs comparison.
    """
    max_mismatch = max(_max_mismatches(num_perm, threshold), 0)
    rows = max(1, num_perm // (max_mismatch + 1))
    bands = num_perm // rows
    return bands, rows


def _band_candidates(
    signatures: dict[str, MinHashSignature],
    num_perm: int,
    threshold: float,
) -> set[tuple[str, str]]:
    """Return candidate (path, path) pairs that collide in at least one LSH band.

    This is the locality-sensitive filter that avoids comparing every pair.
    Band-hash collisions are only *candidates*; the caller still verifies true
    MinHash similarity before unioning, so precision is unchanged. The band
    layout from :func:`_choose_bands` guarantees every pair that would pass
    verification is a candidate, so recall is unchanged too.
    """
    bands, rows = _choose_bands(num_perm, threshold)

    candidates: set[tuple[str, str]] = set()
    for band_idx in range(bands):
        start = band_idx * rows
        end = start + rows
        buckets: dict[tuple[int, ...], list[str]] = {}
        for path, sig in signatures.items():
            # Key on the exact slice of the signature belonging to this band.
            buckets.setdefault(sig.values[start:end], []).append(path)
        for group in buckets.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    candidates.add((a, b) if a < b else (b, a))
    return candidates


def find_near_duplicates(
    file_texts: dict[str, str],
    *,
    threshold: float = 0.8,
    num_perm: int = 128,
    ngram_size: int = 3,
    use_lsh: bool = True,
) -> TextDedupResult:
    """Find near-duplicate text files using MinHash.

    Args:
        file_texts: Mapping of file path to file text content.
        threshold: Jaccard similarity threshold for near-duplicate detection.
        num_perm: Number of hash permutations.
        ngram_size: Character n-gram size.
        use_lsh: When True (default), restrict pairwise comparisons to LSH band
            candidates. The band layout guarantees the same result as the
            exhaustive comparison; it only skips pairs that cannot pass. How
            many pairs it skips depends on the threshold (fewer at low
            thresholds). Set False to force the exhaustive all-pairs comparison.

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

    # --- Candidate generation ---
    # With LSH banding we only verify pairs that collide in >=1 band. The band
    # layout (see _choose_bands) guarantees every pair that can pass the
    # threshold collides somewhere, so results match the exhaustive path. At
    # threshold 0 every pair passes, so banding is skipped.
    candidate_pairs: set[tuple[str, str]] | None = None
    if use_lsh and len(paths) > 2 and threshold > 0.0:
        candidate_pairs = _band_candidates(signatures, num_perm, threshold)

    # --- Pairwise verification (exact MinHash similarity) ---
    scores: dict[str, float] = {}
    if candidate_pairs is not None:
        pair_iter = iter(sorted(candidate_pairs))
    else:
        pair_iter = (
            (paths[i], paths[j])
            for i in range(len(paths))
            for j in range(i + 1, len(paths))
        )

    for pa, pb in pair_iter:
        sim = hasher.similarity(signatures[pa], signatures[pb])
        if sim >= threshold:
            # Order-independent key so LSH and exhaustive paths agree.
            pair_key = f"{pa}|{pb}" if pa < pb else f"{pb}|{pa}"
            scores[pair_key] = round(sim, 4)
            union(pa, pb)

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


def load_text_files(root: Path, rel_paths: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    """Read files under *root* that look like UTF-8 text.

    A file is treated as text when it contains no NUL byte and decodes as
    strict UTF-8. Everything else (images, audio, other binaries) is skipped.
    All accepted texts are held in memory, so bound the input size with the
    scanner's ``max_file_size`` / ``extensions`` options on large datasets.

    Args:
        root: Directory the relative paths are resolved against.
        rel_paths: Paths relative to *root* (for example the keys of a scan
            result's ``files`` manifest).

    Returns:
        ``(texts, skipped)``: a ``{rel_path: text}`` mapping and the sorted
        list of paths skipped as non-text or unreadable.
    """
    texts: dict[str, str] = {}
    skipped: list[str] = []
    for rel in rel_paths:
        try:
            data = (root / rel).read_bytes()
        except OSError:
            skipped.append(rel)
            continue
        if b"\x00" in data:
            skipped.append(rel)
            continue
        try:
            texts[rel] = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append(rel)
    return texts, sorted(skipped)
