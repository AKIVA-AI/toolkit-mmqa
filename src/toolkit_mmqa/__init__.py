"""Toolkit Multimodal Dataset QA — dataset scanning, hashing, and deduplication.

This package provides dataset QA utilities (files are compared as bytes;
image/audio-aware checks are not implemented):

- **Train/eval and benchmark contamination** (exact, word n-gram, MinHash)
- **Record-level dedup** for JSONL / JSON / CSV / text datasets
- **Exact duplicate detection** via SHA-256 file hashing
- **Near-duplicate text detection** via MinHash (Jaccard similarity)
- **Report generation** with summary statistics
- **File-level scan diff** (added / removed / modified files)
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

from ._version import __version__
from .contamination import ContaminationResult, Target, check_contamination
from .dedup import DedupResult, SourceRecords, dedup_records
from .records import Record, RecordError, load_records
from .reporting import DiffResult, ReportSummary, diff_scans, generate_report
from .scanner import ScanMetadata, ScanResult, scan
from .text_dedup import MinHasher, TextDedupResult, find_near_duplicates

__all__ = [
    "__version__",
    "ContaminationResult",
    "DedupResult",
    "SourceRecords",
    "dedup_records",
    "Record",
    "RecordError",
    "Target",
    "check_contamination",
    "load_records",
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
