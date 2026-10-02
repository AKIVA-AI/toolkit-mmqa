"""Benchmark MinHash signatures: pure Python vs NumPy (the ``[fast]`` extra).

Usage::

    pip install -e ".[fast]"
    python benchmarks/bench_minhash.py [--docs 2000] [--words 150]

Generates synthetic documents (random words from a 5,000-word vocabulary) and
times ``MinHasher.signature`` with 128 permutations on each path. Both paths
produce identical signatures; the script checks that too.
"""

from __future__ import annotations

import argparse
import platform
import random
import time

from toolkit_mmqa.text_dedup import MinHasher


def _docs(n: int, words: int, seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    vocab = [f"w{i}" for i in range(5000)]
    return [" ".join(rng.choices(vocab, k=words)) for _ in range(n)]


def _time(hasher: MinHasher, docs: list[str]) -> tuple[float, list]:
    start = time.perf_counter()
    sigs = [hasher.signature(d) for d in docs]
    return time.perf_counter() - start, sigs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--docs", type=int, default=2000)
    p.add_argument("--words", type=int, default=150)
    p.add_argument("--num-perm", type=int, default=128)
    args = p.parse_args()

    docs = _docs(args.docs, args.words)
    chars = sum(len(d) for d in docs) / len(docs)
    print(f"python {platform.python_version()}, {args.docs} docs, ~{chars:.0f} chars each")
    slow_t, slow = _time(MinHasher(num_perm=args.num_perm, use_numpy=False), docs)
    print(f"pure Python : {slow_t:7.2f} s  ({args.docs / slow_t:8.0f} docs/s)")
    try:
        fast_t, fast = _time(MinHasher(num_perm=args.num_perm, use_numpy=True), docs)
    except RuntimeError:
        print("numpy       : not installed (pip install '.[fast]')")
        return
    print(f"numpy       : {fast_t:7.2f} s  ({args.docs / fast_t:8.0f} docs/s)")
    print(f"speed-up    : {slow_t / fast_t:5.1f}x, identical signatures: {slow == fast}")


if __name__ == "__main__":
    main()
