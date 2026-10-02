"""Image checks: corrupt files, resolution statistics, perceptual-hash near-duplicates.

Reference implementation: the ``imagehash`` library (J. Buchner, BSD-2-Clause),
whose ``phash`` / ``dhash`` follow Neal Krawetz, "Looks Like It" and "Kind of
Like That" (hackerfactor.com). Our Pillow-only hashes must equal imagehash's
bit for bit on the generated test images.
"""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from toolkit_mmqa.cli import main  # noqa: E402
from toolkit_mmqa.images import (  # noqa: E402
    check_images,
    dhash_hex,
    hamming,
    near_duplicate_pairs,
    phash_hex,
)


def _picture(seed: int, size: tuple[int, int] = (160, 120)) -> Image.Image:
    """A smooth synthetic 'photo': gradient background plus random shapes."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    c1 = [rng.randrange(256) for _ in range(3)]
    c2 = [rng.randrange(256) for _ in range(3)]
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2, strict=True))
    draw = ImageDraw.Draw(img)
    for _ in range(6):
        x0, y0 = rng.randrange(w), rng.randrange(h)
        x1, y1 = x0 + rng.randrange(20, 80), y0 + rng.randrange(20, 60)
        color = tuple(rng.randrange(256) for _ in range(3))
        if rng.random() < 0.5:
            draw.ellipse((x0, y0, x1, y1), fill=color)
        else:
            draw.rectangle((x0, y0, x1, y1), fill=color)
    return img


def _jpeg_roundtrip(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


# --- reference comparison -----------------------------------------------------


@pytest.mark.parametrize("seed", range(8))
def test_hashes_equal_imagehash_reference(seed: int) -> None:
    imagehash = pytest.importorskip("imagehash")
    img = _picture(seed)
    assert phash_hex(img) == str(imagehash.phash(img))
    assert dhash_hex(img) == str(imagehash.dhash(img))


def test_resized_and_recompressed_copies_stay_close() -> None:
    base = _picture(1)
    h0 = phash_hex(base)
    assert hamming(h0, phash_hex(base.resize((80, 60)))) <= 4
    assert hamming(h0, phash_hex(_jpeg_roundtrip(base, 60))) <= 4
    others = [hamming(h0, phash_hex(_picture(s))) for s in range(2, 8)]
    assert min(others) > 8


def test_near_duplicate_pairs_equal_brute_force() -> None:
    """Pigeonhole bucketing finds exactly the pairs within the distance."""
    rng = random.Random(5)
    base = [rng.getrandbits(64) for _ in range(20)]
    hashes = {}
    for i, b in enumerate(base):
        hashes[f"{i}"] = f"{b:016x}"
        flipped = b
        for bit in rng.sample(range(64), rng.randint(0, 12)):
            flipped ^= 1 << bit
        hashes[f"{i}v"] = f"{flipped:016x}"
    for d in (0, 3, 8, 12):
        keys = sorted(hashes)
        expected = sorted(
            (a, b, hamming(hashes[a], hashes[b]))
            for i, a in enumerate(keys)
            for b in keys[i + 1 :]
            if hamming(hashes[a], hashes[b]) <= d
        )
        assert near_duplicate_pairs(hashes, d) == expected


# --- check_images and CLI -----------------------------------------------------


def _dataset(root: Path) -> Path:
    root.mkdir()
    base = _picture(1)
    base.save(root / "photo.png")
    base.resize((80, 60)).save(root / "photo_small.jpg", quality=85)
    _picture(2).save(root / "other.png")
    good = io.BytesIO()
    _picture(3).save(good, format="JPEG")
    (root / "truncated.jpg").write_bytes(good.getvalue()[: len(good.getvalue()) // 2])
    (root / "not_an_image.png").write_bytes(b"this is text, not a PNG")
    (root / "notes.txt").write_text("not an image file", encoding="utf-8")
    return root


def test_check_images_finds_corrupt_and_near_duplicates(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "ds")
    files = [p.name for p in root.iterdir()]
    result = check_images(root, files)
    assert result.checked_count == 5
    assert [c["path"] for c in result.corrupt] == ["not_an_image.png", "truncated.jpg"]
    assert result.near_duplicate_groups == [["photo.png", "photo_small.jpg"]]
    res = result.resolution()
    assert res["width"] == {"min": 80, "median": 160, "max": 160}
    assert res["height"]["min"] == 60
    assert result.hashes["photo.png"]["width"] == 160


def test_cli_scan_image_checks_and_gate(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "ds")
    out = tmp_path / "scan.json"
    code = main(
        ["scan", "--root", str(root), "--image-checks", "--out", str(out)]
        + ["--fail-on", "corrupt-media,image-near-duplicates"]
    )
    assert code == 1
    pred = json.loads(out.read_bytes())["predicate"]
    assert pred["summary"]["image_count"] == 5
    assert pred["summary"]["corrupt_media_count"] == 2
    assert pred["summary"]["image_near_duplicate_group_count"] == 1
    assert pred["summary"]["failed_checks"] == ["corrupt-media", "image-near-duplicates"]
    assert pred["details"]["images"]["hash"] == "phash"


def test_cli_scan_image_distance_zero_only_identical(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "ds")
    out = tmp_path / "scan.json"
    code = main(
        ["scan", "--root", str(root), "--image-checks", "--image-hash-distance", "0"]
        + ["--out", str(out)]
    )
    assert code == 0
    images = json.loads(out.read_bytes())["predicate"]["details"]["images"]
    for group in images["near_duplicate_groups"]:  # only hash-identical images group
        assert len({images["hashes"][p]["phash"] for p in group}) == 1
    for pair in images["near_duplicate_pairs"]:
        assert pair["distance"] == 0


@pytest.mark.parametrize(
    "extra",
    [
        ["--fail-on", "corrupt-media"],  # needs --image-checks
        ["--image-checks", "--image-hash-distance", "65"],
    ],
)
def test_cli_scan_image_usage_errors(tmp_path: Path, extra: list[str]) -> None:
    root = _dataset(tmp_path / "ds")
    assert main(["scan", "--root", str(root), *extra]) == 2
