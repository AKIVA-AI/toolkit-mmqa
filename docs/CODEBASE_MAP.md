# toolkit-mmqa Codebase Map

**System:** toolkit-mmqa (TK-08)
**Archetype:** 9 -- Developer Tool / CLI Utility
**Last Updated:** 2026-04-04

## Directory Structure

```
toolkit-mmqa/
  src/toolkit_mmqa/           # Package source
    __init__.py               # Public API exports (__all__, __version__)
    __main__.py               # python -m toolkit_mmqa entry point
    cli.py                    # CLI argument parsing, subcommands, JSONFormatter
    scanner.py                # Directory scanning, SHA-256 dedup, ScanResult/ScanMetadata
    hashing.py                # SHA-256 streaming file hashing (1MB chunks)
    reporting.py              # ReportSummary, DiffResult, load_scan_file
    text_dedup.py             # MinHash near-duplicate text detection (Jaccard similarity)
    signing.py                # Ed25519 signing/verification (optional cryptography dep)
    control_plane/            # Akiva control-plane adapter
      __init__.py             # Re-exports
      contracts.py            # PermissionScope, ApprovalPolicy, AuthorityBoundary, ToolSpec
      config.py               # ToolkitConfigContract, 3-tier config hierarchy
      tool_specs.py           # 4 ToolSpecs: scan, report, diff, verify
  tests/                      # Test suite (229 tests, 86.79% coverage)
    conftest.py               # Shared fixtures
    test_scan.py              # Core scan functionality
    test_scan_edge_cases.py   # Empty dirs, binary, dotfiles, symlinks, frozen dataclass
    test_enhancements.py      # Directory validation, filtering, CLI, full workflow
    test_cli_integration.py   # End-to-end CLI tests (12 tests)
    test_text_dedup.py        # MinHash n-grams, signatures, similarity, grouping
    test_reporting.py         # Report generation, diff, file loading
    test_quality_gates.py     # Hashing, dedup, MinHash edges, validation, provenance
    test_sprint1_hardening.py # Progress bar, max file size, symlinks, JSON logging, signing
    test_control_plane.py     # Permissions, approval, authority, config, tool specs
    test_public_api.py        # Public API exports, programmatic usage
  .github/
    workflows/ci.yml          # CI: test (matrix 3.10-3.12), security, lint+pyright, SBOM, build
    dependabot.yml            # Weekly pip + github-actions updates
    ISSUE_TEMPLATE/           # Bug report + feature request templates
    PULL_REQUEST_TEMPLATE.md  # PR checklist
  docs/
    CODEBASE_MAP.md           # This file
    audits/                   # Audit reports
  pyproject.toml              # Package config, deps, tool settings
  pyrightconfig.json          # Type checking config (excludes control_plane)
  Dockerfile                  # python:3.11-slim container
  docker-compose.yml          # Local Docker setup
```

## Module Dependency Graph

```
hashing.py          (no internal deps)
    |
scanner.py          (imports hashing)
    |
cli.py              (imports scanner, reporting, signing)
    |
reporting.py        (no internal deps)
text_dedup.py       (no internal deps)
signing.py          (no internal deps, optional cryptography)
control_plane/      (no internal deps, optional akiva_execution_contracts)
```

## Key Data Types

| Type | Module | Purpose |
|------|--------|---------|
| `ScanResult` | scanner.py | Scan output: file_count, total_bytes, duplicates, skipped counts, metadata |
| `ScanMetadata` | scanner.py | Provenance: tool_version, scanned_root, timestamp, filters |
| `ReportSummary` | reporting.py | Summary stats from a scan result |
| `DiffResult` | reporting.py | Comparison of two scan results |
| `MinHashSignature` | text_dedup.py | MinHash signature for a document |
| `TextDedupResult` | text_dedup.py | Near-duplicate groups + similarity scores |
| `KeyPair` | signing.py | Ed25519 private/public key pair |
| `ToolkitConfigContract` | control_plane/config.py | Resolved 3-tier configuration |
| `ToolkitCommandSpec` | control_plane/tool_specs.py | CLI command -> ToolSpec + AuthorityBoundary |

## CLI Commands

| Command | Entry Point | Description |
|---------|-------------|-------------|
| `toolkit-mmqa scan` | `cli._cmd_scan` | Scan directory, detect exact duplicates |
| `toolkit-mmqa report` | `cli._cmd_report` | Generate summary from scan result |
| `toolkit-mmqa diff` | `cli._cmd_diff` | Compare two scan results |
| `toolkit-mmqa verify` | `cli._cmd_verify` | Verify Ed25519 signature of scan result |

## Dependencies

- **Core:** None (stdlib only)
- **Optional:** `cryptography>=41.0.0` (Ed25519 signing)
- **Dev:** pytest, pytest-cov, ruff, pyright, cryptography
