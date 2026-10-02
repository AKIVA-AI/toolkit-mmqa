"""Image checks: decode errors, resolution statistics and perceptual near-duplicates.

Needs Pillow (``pip install "toolkit-mmqa[image]"``).

Perceptual hashes follow the definitions used by the ``imagehash`` library
(the tests compare bit for bit against it):

* **dHash** (difference hash): grayscale, resize to 9x8 with Lanczos, and set a
  bit where a pixel is brighter than its left neighbour.
* **pHash** (perceptual hash): grayscale, resize to 32x32 with Lanczos, take the
  2-D DCT-II, keep the top-left 8x8 low-frequency block and set a bit where a
  coefficient is above the block's median.

Hashes are 64-bit and printed as 16 hex digits, row-major, first bit most
significant. Two images are near-duplicates when the Hamming distance of their
pHashes is at most ``max_distance``. Candidate pairs come from the pigeonhole
principle (split the hash into ``max_distance + 1`` bit chunks; a pair within
the distance agrees exactly on at least one chunk), so no pair within the
distance is missed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

IMAGE_EXTENSIONS = frozenset(
    {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff", "ppm", "pgm", "pbm"}
)
DEFAULT_MAX_DISTANCE = 8
HASH_SIZE = 8
_PHASH_SIZE = HASH_SIZE * 4  # 32x32 input for the DCT


def _require_pillow() -> Any:
    try:
        from PIL import Image
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "image checks need Pillow: pip install 'toolkit-mmqa[image]'"
        ) from e
    return Image


def _bits_to_hex(bits: list[bool]) -> str:
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:0{math.ceil(len(bits) / 4)}x}"


def dhash_hex(image: Any) -> str:
    """dHash of a PIL image as 16 hex digits."""
    Image = _require_pillow()
    small = image.convert("L").resize((HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS)
    px = list(small.tobytes())  # mode "L": one byte per pixel
    w = HASH_SIZE + 1
    bits = [px[r * w + c + 1] > px[r * w + c] for r in range(HASH_SIZE) for c in range(HASH_SIZE)]
    return _bits_to_hex(bits)


_COS = [
    [math.cos(math.pi * k * (2 * n + 1) / (2 * _PHASH_SIZE)) for n in range(_PHASH_SIZE)]
    for k in range(HASH_SIZE)
]


def phash_hex(image: Any) -> str:
    """pHash of a PIL image as 16 hex digits."""
    Image = _require_pillow()
    small = image.convert("L").resize((_PHASH_SIZE, _PHASH_SIZE), Image.Resampling.LANCZOS)
    px = list(small.tobytes())  # mode "L": one byte per pixel
    n = _PHASH_SIZE
    rows = [px[r * n : (r + 1) * n] for r in range(n)]
    # DCT-II along columns (axis 0), keeping the first HASH_SIZE coefficients.
    col = [[sum(c[i] * rows[i][j] for i in range(n)) for j in range(n)] for c in _COS]
    # Then along rows (axis 1). Constant scale factors do not change the bits.
    low = [[sum(c[j] * col[k][j] for j in range(n)) for c in _COS] for k in range(HASH_SIZE)]
    flat = [v for row in low for v in row]
    med = median(flat)
    return _bits_to_hex([v > med for v in flat])


def hamming(a: str, b: str) -> int:
    """Number of differing bits between two hex hashes."""
    return (int(a, 16) ^ int(b, 16)).bit_count()


@dataclass
class ImageCheckResult:
    """Outcome of :func:`check_images`."""

    checked_count: int = 0
    corrupt: list[dict[str, str]] = field(default_factory=list)
    hashes: dict[str, dict[str, Any]] = field(default_factory=dict)
    near_duplicate_groups: list[list[str]] = field(default_factory=list)
    near_duplicate_pairs: list[dict[str, Any]] = field(default_factory=list)
    max_distance: int = DEFAULT_MAX_DISTANCE

    def resolution(self) -> dict[str, Any]:
        widths = [h["width"] for h in self.hashes.values()]
        heights = [h["height"] for h in self.hashes.values()]
        if not widths:
            return {}
        return {
            "width": {"min": min(widths), "median": median(widths), "max": max(widths)},
            "height": {"min": min(heights), "median": median(heights), "max": max(heights)},
            "pixels_min": min(w * h for w, h in zip(widths, heights, strict=True)),
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "checked_count": self.checked_count,
            "decoded_count": len(self.hashes),
            "corrupt": self.corrupt,
            "resolution": self.resolution(),
            "hash": "phash",
            "max_distance": self.max_distance,
            "near_duplicate_groups": self.near_duplicate_groups,
            "near_duplicate_pairs": self.near_duplicate_pairs,
            "hashes": self.hashes,
        }


def _decode(path: Path) -> tuple[Any, str | None]:
    """Fully decode *path*; return ``(image, None)`` or ``(None, error)``."""
    Image = _require_pillow()
    try:
        with Image.open(path) as probe:
            probe.verify()  # structure / checksum problems
        img = Image.open(path)
        img.load()  # full decode: catches truncated data
        return img, None
    except Exception as e:  # Pillow raises many exception types for bad files
        return None, f"{type(e).__name__}: {e}"


def _chunks(value: int, parts: int, bits: int = 64) -> list[tuple[int, int]]:
    """Split a *bits*-bit value into *parts* contiguous chunks ``(chunk_no, chunk)``."""
    out = []
    start = 0
    for p in range(parts):
        width = bits // parts + (1 if p < bits % parts else 0)
        out.append((p, (value >> (bits - start - width)) & ((1 << width) - 1)))
        start += width
    return out


def near_duplicate_pairs(hashes: dict[str, str], max_distance: int) -> list[tuple[str, str, int]]:
    """All pairs of keys whose hashes differ in at most *max_distance* bits."""
    if max_distance < 0:
        raise ValueError(f"max_distance must be >= 0, got {max_distance}")
    parts = min(max_distance + 1, 64)
    buckets: dict[tuple[int, int], list[str]] = {}
    for key, hx in hashes.items():
        for chunk in _chunks(int(hx, 16), parts):
            buckets.setdefault(chunk, []).append(key)
    seen: set[tuple[str, str]] = set()
    pairs = []
    for members in buckets.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = sorted((members[i], members[j]))
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                d = hamming(hashes[a], hashes[b])
                if d <= max_distance:
                    pairs.append((a, b, d))
    return sorted(pairs)


def check_images(
    root: Path, rel_paths: Iterable[str], *, max_distance: int = DEFAULT_MAX_DISTANCE
) -> ImageCheckResult:
    """Decode every image among *rel_paths*, hash it and group near-duplicates."""
    _require_pillow()
    result = ImageCheckResult(max_distance=max_distance)
    for rel in sorted(rel_paths):
        if Path(rel).suffix.lower().lstrip(".") not in IMAGE_EXTENSIONS:
            continue
        result.checked_count += 1
        img, error = _decode(root / rel)
        if img is None:
            result.corrupt.append({"path": rel, "error": error or "unknown"})
            continue
        with img:
            result.hashes[rel] = {
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "phash": phash_hex(img),
                "dhash": dhash_hex(img),
            }

    pairs = near_duplicate_pairs({k: v["phash"] for k, v in result.hashes.items()}, max_distance)
    parent = {k: k for k in result.hashes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, d in pairs:
        parent[find(a)] = find(b)
        result.near_duplicate_pairs.append({"a": a, "b": b, "distance": d})
    groups: dict[str, list[str]] = {}
    for k in result.hashes:
        groups.setdefault(find(k), []).append(k)
    result.near_duplicate_groups = sorted(
        (sorted(g) for g in groups.values() if len(g) > 1), key=lambda g: (-len(g), g[0])
    )
    return result
