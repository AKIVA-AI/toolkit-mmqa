# toolkit-mmqa Codebase Map

## Directory structure

```text
toolkit-mmqa/
  src/toolkit_mmqa/
    __init__.py        # Public API exports (__all__, __version__)
    __main__.py        # python -m toolkit_mmqa entry point
    _version.py        # Single source of the package version
    cli.py             # argparse CLI: scan, report, diff, verify; --format/--fail-on; JSON logs
    sources.py         # Record sources: files or Hub datasets (hf:NAME[:CONFIG]:SPLIT)
    records.py         # Read text records from JSONL / JSON / CSV / text (fail-closed)
    audio.py           # Audio decode checks and durations (wave; soundfile optional)
    images.py          # Image decode checks, resolution stats, pHash/dHash near-dups (Pillow)
    dedup.py           # Record-level exact + near-duplicate dedup
    contamination.py   # Train/eval + benchmark contamination (exact, n-gram, MinHash)
    envelope.py        # Report envelope v1 (in-toto Statement), canonical JSON, dataset digest
    scanner.py         # Directory walk, SHA-256 per file, duplicate groups, per-file manifest
    hashing.py         # Streaming SHA-256 (1 MB chunks)
    reporting.py       # ReportSummary, DiffResult (file-level diff), load_scan_file
    text_dedup.py      # MinHash (NumPy-vectorized when available) + LSH, load_text_files
    signing.py         # Ed25519 sign/verify (optional `cryptography` dependency)
  tests/
    conftest.py              # Shared fixtures
    test_scan.py             # Scan, manifest, CLI diff end to end
    test_scan_edge_cases.py  # Empty dirs, binary, dotfiles, symlinks
    test_scan_validation.py  # Directory validation, filtering, full workflow
    test_cli_integration.py  # End-to-end CLI tests
    test_cli_near_dup.py     # scan --near-dup-text / --near-dup-threshold
    test_text_dedup.py       # n-grams, signatures, grouping, LSH recall guarantee
    test_reporting.py        # Report, file-level diff, scan loading
    test_hashing_dedup_and_provenance.py # Hashing, dedup, validation, provenance
    test_scan_options_and_signing.py # Progress bar, max file size, symlinks, JSON logs, signing
    test_public_api.py       # Public API exports
    test_sources.py          # File / Hub sources (fake and real `datasets`), digests
    test_records.py          # Record readers
    test_contamination.py    # Contamination vs brute-force reference, worked example, CLI
    test_audio.py            # Audio checks; stdlib vs libsndfile reference; CLI gate
    test_images.py           # Image checks; hashes vs imagehash reference; CLI gate
    test_dedup.py            # Record dedup vs exact Jaccard, CLI, deduplicated copy
    test_envelope.py         # Envelope shape, JSON Schema validation, gate, signing
    helpers.py               # payload(): unwrap a report envelope in tests
  .github/
    workflows/ci.yml   # test (3.10-3.12), test-core (no extras), action smoke test,
                       # security (bandit), lint + pyright, SBOM, build
    workflows/release.yml  # v* tag: GitHub Release; PyPI upload when PUBLISH_TO_PYPI is true
  action.yml           # Composite GitHub Action wrapping the CLI
    dependabot.yml     # Weekly grouped pip + github-actions updates
  benchmarks/bench_minhash.py   # Pure Python vs NumPy MinHash timing
  docs/report-envelope.md       # Shared report envelope spec
  docs/benchmarks.md            # Fetching public benchmarks for contamination checks
  schemas/report-envelope.v1.json  # JSON Schema for the envelope
  pyproject.toml       # Package metadata, extras, tool settings
  pyrightconfig.json   # Type-check config
  Dockerfile, docker-compose.yml
```

## Module dependency graph

```text
_version.py, hashing.py, text_dedup.py, signing.py   (no internal deps)
envelope.py  -> _version
reporting.py -> envelope
records.py   (no internal deps)
sources.py   -> envelope, records (datasets imported lazily)
contamination.py -> records, text_dedup
dedup.py     -> contamination, records, text_dedup
images.py    (no internal deps; Pillow imported lazily)
audio.py     (no internal deps; soundfile imported lazily)
scanner.py   -> hashing, _version
cli.py       -> envelope, contamination, dedup, images, audio, records, sources, scanner, reporting, text_dedup, signing (lazy import)
__init__.py  -> _version, scanner, reporting, text_dedup
```

## Key data types

| Type | Module | Purpose |
|------|--------|---------|
| `ScanResult` | scanner.py | Counts, duplicate groups, per-file manifest (`files`), skip counters, metadata |
| `ScanMetadata` | scanner.py | Tool version, scanned root, timestamp, filters |
| `ReportSummary` | reporting.py | Summary statistics from a scan |
| `DiffResult` | reporting.py | Added / removed / modified files and duplicate-group changes |
| `MinHashSignature` | text_dedup.py | MinHash signature of one document |
| `TextDedupResult` | text_dedup.py | Near-duplicate groups and pairwise scores |
| `KeyPair` | signing.py | Ed25519 private/public PEM pair |

## CLI commands

| Command | Entry point | Description |
|---------|-------------|-------------|
| `scan` | `cli._cmd_scan` | Hash files, group exact duplicates, optional near-dup text and signing |
| `report` | `cli._cmd_report` | Summary statistics from a scan |
| `diff` | `cli._cmd_diff` | File-level comparison of two scans |
| `contamination` | `cli._cmd_contamination` | Eval/benchmark records found in training data; CI gate |
| `dedup` | `cli._cmd_dedup` | Duplicate / near-duplicate records; deduplicated copy |
| `verify` | `cli._cmd_verify` | Check the Ed25519 signature of a scan |

## Dependencies

- Core: none (stdlib only)
- Optional: `cryptography>=41` (`[signing]`), `pillow>=9.1` (`[image]`), `soundfile>=0.12` (`[audio]`), `numpy>=1.22` (`[fast]`), `datasets>=2.14` (`[hf]`)
- Dev: pytest, pytest-cov, ruff, pyright, cryptography, jsonschema, pillow, imagehash (test reference), soundfile, numpy, datasets
