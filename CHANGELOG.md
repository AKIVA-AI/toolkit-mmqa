# Changelog

All notable changes to toolkit-mmqa are documented in this file.

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
