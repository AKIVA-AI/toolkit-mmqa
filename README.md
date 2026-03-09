# Toolkit Multimodal Dataset QA (Enterprise Tool)

Quick dataset QA utilities:

- Scan a directory tree and compute file hashes
- Detect exact duplicate files via SHA-256
- Detect near-duplicate text files via MinHash (Jaccard similarity)
- Generate summary reports from scan results
- Compare scan results to track changes over time

The core is dependency-free (works for any file types). Text-level deduplication uses MinHash for near-duplicate detection.

## Install

```bash
pip install -e ".[dev]"
```

## CLI Reference

### Global Flags

| Flag | Description |
|------|-------------|
| `--version` | Print version and exit |
| `--verbose`, `-v` | Enable verbose logging (DEBUG level) |

### `scan` — Scan a directory for duplicate files

```bash
toolkit-mmqa scan --root ./dataset --out report.json
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--root` | Yes | — | Root directory to scan recursively |
| `--out` | No | stdout | Output file path for JSON report |
| `--extensions` | No | all | Comma-separated file extensions to include (e.g., `txt,jpg,png`) |

**Examples:**

```bash
# Scan all files in a directory, print to stdout
toolkit-mmqa scan --root ./my-dataset

# Scan only images, save to file
toolkit-mmqa scan --root ./my-dataset --extensions jpg,png,gif --out images.json

# Verbose mode for debugging
toolkit-mmqa --verbose scan --root ./my-dataset --out report.json
```

### `report` — Generate summary statistics

```bash
toolkit-mmqa report --input scan.json --out summary.json
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--input` | Yes | — | Path to a scan result JSON file |
| `--out` | No | stdout | Output file path for summary report |

### `diff` — Compare two scan results

```bash
toolkit-mmqa diff --old scan_v1.json --new scan_v2.json --out changes.json
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--old` | Yes | — | Path to the older scan result JSON file |
| `--new` | Yes | — | Path to the newer scan result JSON file |
| `--out` | No | stdout | Output file path for diff report |

### `--version`

```bash
toolkit-mmqa --version
# toolkit-mmqa 0.1.0
```

## Output Formats

### Scan Output (`scan`)

```json
{
  "duplicates": [
    [
      "images/photo_copy.jpg",
      "images/photo_original.jpg"
    ],
    [
      "docs/readme.txt",
      "docs/readme_backup.txt"
    ]
  ],
  "file_count": 150,
  "total_bytes": 52428800
}
```

| Field | Type | Description |
|-------|------|-------------|
| `file_count` | `int` | Total number of files scanned |
| `total_bytes` | `int` | Total size of all scanned files in bytes |
| `duplicates` | `list[list[str]]` | Groups of files with identical SHA-256 hashes. Each group contains 2+ relative file paths. Sorted by group size (largest first). |

### Report Output (`report`)

```json
{
  "avg_file_size": 349525.33,
  "duplicate_file_count": 4,
  "duplicate_group_count": 2,
  "file_count": 150,
  "largest_group_size": 3,
  "total_bytes": 52428800,
  "unique_file_count": 146
}
```

| Field | Type | Description |
|-------|------|-------------|
| `file_count` | `int` | Total files scanned |
| `total_bytes` | `int` | Total bytes |
| `duplicate_group_count` | `int` | Number of groups of duplicates |
| `duplicate_file_count` | `int` | Total files that are part of a duplicate group |
| `unique_file_count` | `int` | Files not in any duplicate group |
| `avg_file_size` | `float` | Average file size in bytes |
| `largest_group_size` | `int` | Size of the largest duplicate group |

### Diff Output (`diff`)

```json
{
  "added_duplicate_groups": [
    ["new_dup1.txt", "new_dup2.txt"]
  ],
  "added_files": 5,
  "removed_duplicate_groups": [],
  "removed_files": 0,
  "unchanged_duplicate_groups": [
    ["old_dup1.txt", "old_dup2.txt"]
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `added_files` | `int` | Net new files (new count - old count) |
| `removed_files` | `int` | Net removed files (0 if new >= old) |
| `added_duplicate_groups` | `list[list[str]]` | New duplicate groups not in old scan |
| `removed_duplicate_groups` | `list[list[str]]` | Duplicate groups no longer present |
| `unchanged_duplicate_groups` | `list[list[str]]` | Duplicate groups present in both scans |

## Programmatic API

The library can be used directly from Python:

```python
from toolkit_mmqa import scan, ScanResult, generate_report, find_near_duplicates
from pathlib import Path

# Scan for exact duplicates
result = scan(root=Path("./my-dataset"))
print(f"Found {len(result.duplicates)} duplicate groups in {result.file_count} files")

# Generate a summary report
report = generate_report(result.to_json())
print(f"Unique files: {report.unique_file_count}")

# Near-duplicate text detection via MinHash
texts = {
    "doc1.txt": open("doc1.txt").read(),
    "doc2.txt": open("doc2.txt").read(),
}
dedup = find_near_duplicates(texts, threshold=0.8)
for group in dedup.near_duplicate_groups:
    print(f"Near-duplicates: {group}")
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest -x -q

# Run with coverage
python -m pytest --cov=toolkit_mmqa --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check
pyright src/
```
