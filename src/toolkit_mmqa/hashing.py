"""Cryptographic hashing utilities for file integrity verification.

Provides SHA-256 based file hashing used for exact-duplicate detection.
Files are read in 1 MB chunks to handle arbitrarily large files without
excessive memory consumption.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Default chunk size for streaming file reads (1 MB).
CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file.

    Reads the file in streaming 1 MB chunks so that memory usage stays
    constant regardless of file size.

    Args:
        path: Path to the file to hash.  Must exist and be readable.

    Returns:
        Lowercase hex string of the SHA-256 digest (64 characters).

    Raises:
        FileNotFoundError: If *path* does not exist.
        PermissionError: If the file cannot be read.
        IsADirectoryError: If *path* is a directory.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()
