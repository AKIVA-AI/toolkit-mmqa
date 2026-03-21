"""Toolkit Multimodal Dataset QA — dataset scanning, hashing, and deduplication.

This package provides utilities for quality assurance of multimodal datasets:

- **Exact duplicate detection** via SHA-256 file hashing
- **Near-duplicate text detection** via MinHash (Jaccard similarity)
- **Report generation** with summary statistics
- **Scan comparison** (diff) to track dataset changes over time
- **Ed25519 signing** for scan result integrity verification
- **Data provenance** tracking with scan metadata

Typical usage::

    from toolkit_mmqa import scan, generate_report, find_near_duplicates
    from pathlib import Path

    result = scan(root=Path("./my-dataset"))
    report = generate_report(result.to_json())
    texts = {"a.txt": "hello", "b.txt": "hello world"}
    dedup = find_near_duplicates(texts, threshold=0.8)
"""

from __future__ import annotations

from .reporting import DiffResult, ReportSummary, diff_scans, generate_report
from .scanner import ScanMetadata, ScanResult, scan
from .text_dedup import MinHasher, TextDedupResult, find_near_duplicates

__all__ = [
    "__version__",
    "DiffResult",
    "MinHasher",
    "ReportSummary",
    "ScanMetadata",
    "ScanResult",
    "TextDedupResult",
    "diff_scans",
    "find_near_duplicates",
    "generate_report",
    "scan",
]

__version__ = "0.1.0"
