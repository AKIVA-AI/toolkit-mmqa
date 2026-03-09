from __future__ import annotations

from .reporting import DiffResult, ReportSummary, diff_scans, generate_report
from .scanner import ScanResult, scan
from .text_dedup import MinHasher, TextDedupResult, find_near_duplicates

__all__ = [
    "__version__",
    "DiffResult",
    "MinHasher",
    "ReportSummary",
    "ScanResult",
    "TextDedupResult",
    "diff_scans",
    "find_near_duplicates",
    "generate_report",
    "scan",
]

__version__ = "0.1.0"
