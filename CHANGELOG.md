# Changelog

All notable changes to toolkit-mmqa are documented in this file.

## [1.0.0] - 2026-09-26

First release on PyPI (published 2026-10-02): `pip install toolkit-mmqa`.

The tool is now a dataset pre-flight and contamination check: a zero-GPU QA
gate for fine-tuning and evaluation datasets with a signable report.

### Release and CI

- Version 1.0.0.
- `action.yml`: composite GitHub Action (`args`, `extras`, `report` inputs;
  `verdict`, `report` outputs; Markdown job summary), smoke-tested in CI.
- CI runs the suite with no extras installed to keep the core dependency-free.
- README: a 5-minute example on GSM8K with real output.
- Docker image installs the `image`, `audio`, `fast` and `signing` extras (not
  the dev tools), runs as a non-root user, and uses `toolkit-mmqa` as entrypoint.
- Package metadata: new description, keywords, classifiers, author.
- Release workflow: a `v*` tag runs the tests, builds the sdist and wheel,
  checks them with `twine check --strict` (twine 6.1 or newer, which reads the
  Metadata 2.4 that setuptools 77+ writes), installs the wheel and checks its
  version against the tag, and attaches both files to a GitHub Release. The
  PyPI upload (Trusted Publishing) runs only when the repository variable
  `PUBLISH_TO_PYPI` is `true`. See `RELEASING.md`.
- CI builds and checks the package the same way on every pull request.
- Package metadata: SPDX license expression `Apache-2.0` with `LICENSE` and
  `NOTICE` in the distributions, author AKIVA AI, LLC, and links to the
  documentation, issues and changelog.
- Added `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue and pull request
  templates and `RELEASING.md`. `SECURITY.md` lists the supported versions and
  the private reporting channel.
- CI runs `pip-audit` with every optional extra installed. It replaces a
  `safety check || true` step, which could not fail.

### License

- Relicensed from MIT to Apache-2.0. Releases before this change remain available
  under MIT. Added a `NOTICE` file.

### Contamination

- New `contamination` command: checks evaluation splits (`--eval`) and benchmarks
  (`--benchmark`) against training data (`--train`, repeatable) with `exact`
  (normalized text), `ngram` (word 13-grams, the GPT-3 contamination definition)
  and optional `minhash` (character-trigram Jaccard) methods. Reports every
  contaminated record with the training records it matches; exit 1 when a
  target's contaminated fraction is above `--max-contamination` (default 0).
- Reads JSONL, JSON arrays, CSV and plain text; fail-closed on malformed lines or
  missing fields (exit 2, with an `error` report when `--out` is given).
- `docs/benchmarks.md`: how to fetch GSM8K, HumanEval, MMLU, ARC and HellaSwag
  and which fields to check.

### Hugging Face datasets input

- `contamination --train/--eval/--benchmark` and `dedup --input` accept
  `hf:NAME[:CONFIG]:SPLIT[@REVISION]` with the optional `[hf]` extra; splits are
  streamed. The report records `uri` `hf://datasets/NAME`, the split, config,
  revision and record count, and a SHA-256 over the records read.

### Performance

- Optional `[fast]` extra (NumPy) vectorizes MinHash signatures: about 12x
  faster, bit-identical to the pure-Python path. The hash family is now
  `((a*x + b) mod 2^64) mod p` (the datasketch construction) so both paths
  agree exactly; signatures differ from earlier versions (none are persisted).
- `scan --workers N` hashes files on a thread pool; results are identical.
- `benchmarks/bench_minhash.py` and a README Performance section.

### Audio checks

- `scan --audio-checks`: decodes every audio file to the end and reports corrupt,
  truncated (header frame count above the decoded data) and empty files, with
  duration, sample-rate and channel statistics. PCM WAV needs no dependencies;
  FLAC, Ogg, MP3 and AIFF use the optional `[audio]` extra (soundfile) and are
  listed as `unsupported` without it. `--fail-on corrupt-media` covers audio.
- Video is Planned; video files are compared as bytes only.

### Image checks

- `scan --image-checks` (optional `[image]` extra, Pillow): full decode of every
  image to find corrupt or truncated files, resolution statistics, and 64-bit
  pHash / dHash near-duplicate groups (`--image-hash-distance`, default 8 bits).
  The hashes equal the `imagehash` library's bit for bit (tested). Pair search
  uses pigeonhole bucketing, so no pair within the distance is missed.
- `--fail-on corrupt-media,image-near-duplicates` for CI.

### Record-level dedup

- New `dedup` command: exact (normalized text) and optional near-duplicate
  (MinHash) records across one or more JSONL / JSON / CSV / text files. Groups are
  transitive, the first record of each group is kept, and `--write-deduped`
  writes a byte-for-byte copy of a JSONL or text file without the removable
  records. `--fail-on exact-duplicates,near-duplicates` gates CI.

### Report envelope

- **Breaking:** `scan`, `report` and `diff` write a report envelope by default: an
  in-toto Statement v1 in canonical JSON (spec in `docs/report-envelope.md`, JSON
  Schema in `schemas/report-envelope.v1.json`). The previous objects are under
  `predicate.details` (`scan`, `diff`) or `predicate.summary` (`report`), and
  `--format legacy-json` still prints them for one minor version.
  `--format markdown` prints a human-readable summary.
- The scan subject digest is the SHA-256 of the canonical `{path: sha256}`
  manifest, so a report identifies exactly which file contents were checked.
- `scan --fail-on exact-duplicates,near-duplicates`: CI gate, verdict `fail` and
  exit code 1 when a listed check finds something.
- `scan --sign` writes a detached signature `<out>.sig` over the report bytes;
  `verify` checks it (`--signature`, default `<input>.sig`) and still accepts the
  embedded signature of `--format legacy-json` scans.
- Manifest paths use `/` on every platform.
- `report` and `diff` read both envelope and legacy scan files.

### Fixed

- Near-duplicate text: the LSH band layout dropped most pairs near the threshold
  (about 20% recall for a pair exactly at the default 0.8). Bands are now chosen so
  every pair that passes the threshold is compared; LSH output equals the
  exhaustive comparison.
- `diff` compared file counts (negative "added" on shrink, 0/0 when every file was
  replaced, swaps invisible). It is now a file-level diff: `added_files`,
  `removed_files`, `modified_files` (path lists) and `unchanged_file_count`.
  **Breaking:** these fields were integers; scans without a `files` manifest are
  rejected.
- The version is defined once (`toolkit_mmqa/_version.py`).

### Added

- Scan output includes a per-file manifest: `files: {path: {sha256, size}}`.
  Signed scans now cover file hashes.
- `scan --near-dup-text` and `--near-dup-threshold` expose MinHash near-duplicate
  text detection in the CLI (results under `near_duplicates`).
- `report` emits `unique_content_count` (file count after exact deduplication).

### Removed

- The unused `control_plane` package (agent-platform adapter) and its tests.
- `DEPLOYMENT.md`, `QUICKSTART.md` and `.env.example` (which listed settings that
  do not exist).

### Changed

- README states what works and what is planned. Image, audio and media-quality
  checks are Planned; files of those types are only compared byte for byte.
- Dependabot opens one grouped weekly PR per ecosystem.

## [0.1.0] - 2026-04-04

### Added

- Near-duplicate text detection via MinHash (Jaccard similarity) with configurable parameters
- Ed25519 signing and verification for scan result integrity (`--sign`, `--sign-key`, `verify` subcommand)
- `report` subcommand for summary statistics from scan results
- `diff` subcommand for comparing two scan results
- Data provenance metadata (tool version, timestamp, root path, filter parameters)
- `--max-file-size` flag to skip oversized files
- `--follow-symlinks` / `--skip-symlinks` flags
- `--progress` flag for progress bar display
- `--log-format json` for structured JSON logging
- `--version` flag
- Programmatic API: `scan`, `generate_report`, `diff_scans`, `find_near_duplicates`, `MinHasher`
- Control-plane adapter with ToolSpec definitions for all 4 CLI commands
- 3-tier configuration hierarchy (platform defaults -> toolkit config -> CLI overrides)
- SBOM generation (CycloneDX) in CI pipeline
- Comprehensive test suite (229 tests, 86.79% coverage)
- CI matrix testing (Python 3.10, 3.11, 3.12)
- Dependabot for automated dependency updates

### Initial Capabilities

- SHA-256 exact duplicate detection across directory trees
- Extension filtering for targeted scans
- JSON output for all commands
- Docker support (Dockerfile + docker-compose)
