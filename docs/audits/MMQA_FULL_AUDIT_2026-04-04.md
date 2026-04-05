# toolkit-mmqa Full System Audit Report

**Date:** 2026-04-04
**Auditor:** Claude Code (Automated)
**Baseline:** Source code inspection + test execution
**Archetype:** 9 -- Developer Tool / CLI Utility
**Previous Audit:** [MMQA_AUDIT_REPORT_2026-03-09.md](MMQA_AUDIT_REPORT_2026-03-09.md) (56.3/100)
**Build Standard:** Akiva Build Standard v2.14
**Standards Baseline:** v2.14 (31 standards)
**Declared Agentic Engineering Level:** N/A (CLI tool)
**Declared Agent Runtime Tier:** none

---

## Declared Engineering and Runtime Context

| Field | Value | Evidence |
|-------|-------|----------|
| Agentic Engineering Level | N/A | CLI tool, not agentic |
| Agent Runtime Tier | none | No agent runtime |
| Autonomy Boundary | N/A | Read-only CLI tool |
| Human Approval Required For | N/A | No destructive operations |
| Consequence Matrix | N/A | Read-only analysis tool |
| Tool Registry Status | present | `control_plane/tool_specs.py` -- 4 ToolSpecs |
| Kill Switch / Override Path | N/A | CLI tool, no persistent processes |

## Trust Review Snapshot

| Trust Gate | Result | Evidence |
|-----------|--------|----------|
| T-1 State Transparency | N/A | CLI tool, no persistent state |
| T-2 Override Accessibility | N/A | CLI tool |
| T-3 Autonomy Fit | N/A | No autonomous behavior |
| T-4 High-Risk Action Clarity | N/A | Read-only tool |
| T-5 Error and Recovery Honesty | PASS | Clear error messages, exit codes 0/2/3 |
| T-6 Operational Trust Discipline | N/A | Not deployed as service |
| T-7 Consequence Classification | N/A | No consequential actions |

## Resilience Review Snapshot

| Resilience Gate | Result | Evidence |
|----------------|--------|----------|
| R-1 Confidence Thresholds | N/A | CLI tool, no AI confidence scoring |
| R-2 Degradation Testing | N/A | No degradation modes |
| R-3 Friction Telemetry | N/A | CLI tool |
| R-4 Flow SLOs | N/A | CLI tool |
| R-5 Feedback Discipline | N/A | CLI tool |
| R-6 Business-Context Alignment | N/A | CLI tool |

---

## Verification Evidence

```
$ pytest --cov=toolkit_mmqa --cov-report=term-missing -v
229 passed, 4 skipped in 1.72s
Total coverage: 86.79% (threshold: 80%)

$ ruff check src/ tests/
All checks passed!

$ pyright src/
0 errors, 7 warnings (optional cryptography dependency -- expected)
  - control_plane excluded per CI pattern (pyrightconfig.json)
  - 7 warnings: optional cryptography imports in signing.py
```

---

## Composite Score: 70.5/100

| # | Dimension | Weight | Score | Prior | Delta | Weighted | Status |
|---|-----------|--------|-------|-------|-------|----------|--------|
| 1 | Architecture Integrity | 8% | 8 | 7 | +1 | 6.40 | PASS |
| 2 | Auth & Identity | 2% | 3 | 1 | +2 | 0.60 | -- |
| 3 | Data Isolation & RLS | 0% | 0 | 0 | 0 | 0.00 | N/A |
| 4 | API Surface Quality | 12% | 8 | 6 | +2 | 9.60 | PASS (min 7) |
| 5 | Data Layer Integrity | 2% | 6 | 4 | +2 | 1.20 | -- |
| 6 | Frontend Quality | 0% | 0 | 0 | 0 | 0.00 | N/A |
| 7 | Testing & QA | 15% | 8 | 6 | +2 | 12.00 | PASS (min 7) |
| 8 | Security Posture | 10% | 8 | 6 | +2 | 8.00 | PASS (min 6) |
| 9 | Observability & Monitoring | 5% | 7 | 5 | +2 | 3.50 | -- |
| 10 | CI/CD & Infrastructure | 10% | 8 | 7 | +1 | 8.00 | PASS (min 6) |
| 11 | Documentation Accuracy | 10% | 7 | 5 | +2 | 7.00 | PASS (min 6) |
| 12 | Domain Capability Depth | 8% | 7 | 5 | +2 | 5.60 | PASS (min 6) |
| 13 | AI/ML Capability | 5% | 4 | 3 | +1 | 2.00 | -- |
| 14 | Connectivity & Channel | 2% | 3 | 2 | +1 | 0.60 | -- |
| 15 | Agentic UI/UX | 0% | 0 | 0 | 0 | 0.00 | N/A |
| 16 | UX Quality | 0% | 0 | 0 | 0 | 0.00 | N/A |
| 17 | User Journey | 0% | 0 | 0 | 0 | 0.00 | N/A |
| 18 | Zero Trust Architecture | 2% | 5 | 3 | +2 | 1.00 | -- |
| 19 | Enterprise Security | 5% | 6 | 4 | +2 | 3.00 | -- |
| 20 | Operational Readiness | 2% | 5 | 4 | +1 | 1.00 | -- |
| 21 | Agentic Workspace | 2% | 5 | 2 | +3 | 1.00 | -- |
| | **Total** | **100%** | | | | **70.50** | |

**Prior composite:** 56.3/100 | **Current:** 70.5/100 | **Delta:** +14.2

**Archetype minimum checks:** All PASS (D4=8>=7, D7=8>=7, D8=8>=6, D10=8>=6, D11=7>=6, D12=7>=6). Composite 70.5 >= 60. **All 4 prior violations resolved.**

---

## Dimension 1: Architecture Integrity (Score: 8)

**Weight: 8% | Prior: 7 | Delta: +1**

### Evidence
- Clean `src/toolkit_mmqa` package with 12 source files in logical modules
- Linear dependency chain: `hashing` -> `scanner` -> `cli`; `reporting`, `text_dedup`, `signing` are independent
- `control_plane/` adapter added with 3 modules (contracts, config, tool_specs)
- `pyproject.toml` properly configured: src layout, entry point, zero core deps, optional-deps for signing and dev
- Ruff: 0 errors, 0 warnings
- **Pyright: 0 errors** (control_plane excluded per CI pattern in `pyrightconfig.json`; 7 warnings for optional cryptography -- expected)
- Config hierarchy (3-tier: platform defaults -> toolkit config -> CLI overrides)

### Cap Conditions
- No circular dependencies, no dead code
- Score 9 would require formal architecture documentation or ADR

---

## Dimension 2: Auth & Identity (Score: 3)

**Weight: 2% | Prior: 1 | Delta: +2**

### Evidence
- Ed25519 signing and verification for scan result integrity (`signing.py`, 121 LOC)
- `--sign` and `--sign-key` CLI flags for scan results
- `verify` subcommand for signature validation
- Key pair generation utility (`generate_ed25519_keypair`)
- No user authentication (appropriate for CLI archetype)

### Cap Conditions
- No API auth (no API server mode exists)
- Score appropriate for read-only CLI tool with integrity signing

---

## Dimension 4: API Surface Quality (Score: 8)

**Weight: 12% | Prior: 6 | Delta: +2**

### Evidence
- **4 CLI subcommands:** `scan`, `report`, `diff`, `verify`
- **Global flags:** `--version`, `--verbose/-v`, `--log-format {text,json}`
- **Scan flags:** `--root`, `--out`, `--extensions`, `--max-file-size`, `--follow-symlinks/--skip-symlinks`, `--progress`, `--sign`, `--sign-key`
- Consistent exit codes: 0 (success), 2 (CLI error), 3 (unexpected error)
- JSON output for all commands
- **Programmatic API:** `__init__.py` exports `scan`, `ScanResult`, `ScanMetadata`, `generate_report`, `ReportSummary`, `diff_scans`, `DiffResult`, `find_near_duplicates`, `MinHasher`, `TextDedupResult`
- `__all__` properly defined
- `py.typed` marker for PEP 561

### Cap Conditions
- No text output format for human-readable CLI output (JSON only)
- No shell completion
- `--follow-symlinks` is default True with `store_true` which makes the flag a no-op (already True)

---

## Dimension 5: Data Layer Integrity (Score: 6)

**Weight: 2% | Prior: 4 | Delta: +2**

### Evidence
- SHA-256 streaming file hashing (1MB chunks via `CHUNK_SIZE`)
- `ScanMetadata` provenance: tool version, scanned root, ISO-8601 timestamp, extensions filter, max file size
- JSON serialization roundtrip verified in tests (`test_scan_result_roundtrip`)
- `load_scan_file` validates required keys (file_count, total_bytes, duplicates)
- Canonical JSON serialization for signing (`sort_keys=True, separators=(',', ':')`)

### Cap Conditions
- No incremental scan / hash caching
- No database layer (appropriate for archetype)
- File I/O only (T0/T1 state, appropriate per Build Standard table for Archetype 9)

---

## Dimension 7: Testing & QA (Score: 8)

**Weight: 15% | Prior: 6 | Delta: +2**

### Evidence
- **229 tests passing** (up from 9 at prior audit), 4 skipped (symlink tests on Windows)
- **86.79% branch coverage** (above 80% `fail_under`, above 55% archetype minimum)
- **11 test files** covering all modules:
  - `test_scan.py` -- core scan functionality
  - `test_scan_edge_cases.py` -- empty dirs, binary files, dotfiles, large files, frozen dataclass
  - `test_enhancements.py` -- directory validation, extension filtering, CLI flags, full workflow
  - `test_cli_integration.py` -- 12 CLI integration tests (scan, report, diff, error cases)
  - `test_text_dedup.py` -- MinHash n-grams, signatures, similarity, near-duplicate grouping
  - `test_reporting.py` -- report generation, diff, file loading, edge cases
  - `test_quality_gates.py` -- hashing, duplicate detection, MinHash edge cases, input validation, return types, provenance, governance, configurability
  - `test_sprint1_hardening.py` -- progress bar, max file size, symlinks, JSON logging, signing/verification
  - `test_control_plane.py` -- permissions, approval policy, authority boundary, config hierarchy, tool specs
  - `test_public_api.py` -- public API exports, programmatic scan/report/text dedup
  - `conftest.py` -- shared fixtures
- CI matrix: Python 3.10, 3.11, 3.12 (3 versions)
- Coverage thresholds enforced in CI (`fail_under = 80`)

### Cap Conditions
- No property-based testing (hypothesis)
- No fuzz testing
- Pyright not in CI (type errors not gated)
- 4 symlink tests skipped on Windows (reasonable platform limitation)

---

## Dimension 8: Security Posture (Score: 8)

**Weight: 10% | Prior: 6 | Delta: +2**

### Evidence
- No `eval()`, `exec()`, `shell=True`, or hardcoded secrets in codebase
- CI includes `bandit -r src/` and `safety check`
- Ed25519 signing for report integrity (cryptography lib, optional dep)
- MD5 in MinHash uses `usedforsecurity=False` (PEP 706, non-security-critical)
- Dependabot configured: pip weekly + github-actions weekly
- **SECURITY.md meets Repository Controls v1.3 §1.1** -- supported versions, reporting instructions, 48h/7d response timeline, coordinated disclosure, scope definition
- **SBOM generation in CI** -- CycloneDX via Syft, vulnerability scanning via Grype, artifact published
- `--skip-symlinks` flag prevents symlink traversal
- `--max-file-size` prevents DoS from huge files

### Cap Conditions

- No container image scanning (Dockerfile exists but no Trivy/Snyk)
- No pen test / security review evidence
- Score 9 would require signed commits + container scanning

### Fixable By

- **Human:** Container image scanning, pen test, signed commits

---

## Dimension 9: Observability & Monitoring (Score: 7)

**Weight: 5% | Prior: 5 | Delta: +2**

### Evidence
- Python `logging` throughout (`cli.py`, `scanner.py`)
- `--verbose/-v` flag for DEBUG level output
- **Structured JSON logging:** `--log-format json` produces `{"timestamp", "level", "logger", "message"}` records to stderr (`JSONFormatter` class in `cli.py`)
- **Progress bar:** `--progress` flag shows `[####------] 40% (120/300)` on stderr
- Skip tracking: `skipped_count`, `skipped_oversized`, `skipped_symlinks` in scan results
- Provenance metadata in every scan output

### Cap Conditions
- No metrics export (Prometheus, StatsD)
- No tracing (OpenTelemetry)
- No log aggregation integration
- Appropriate for Archetype 9 -- CLI tools typically don't need metrics/tracing

---

## Dimension 10: CI/CD & Infrastructure (Score: 8)

**Weight: 10% | Prior: 7 | Delta: +1**

### Evidence

- **CI pipeline** (`.github/workflows/ci.yml`):
  - `test` job: matrix (3.10, 3.11, 3.12) with `fail-fast: false`, `pytest --cov`, codecov upload
  - `security` job: `bandit -r src/`, `safety check`
  - `lint` job: `ruff check` + `pyright src/` (type checking gated in CI)
  - `sbom` job: Syft SBOM generation (CycloneDX) + Grype vulnerability scanning + artifact upload
  - `build` job: `python -m build`, `twine check` (depends on test+security+lint+sbom)
  - `all-checks` aggregator job (depends on all 5 jobs, fails if any fail)
- Dependabot: pip + github-actions on weekly schedule
- Dockerfile: `python:3.11-slim`, clean install
- docker-compose.yml with volume mounts
- **Issue/PR templates:** bug report, feature request, PR checklist
- Package builds successfully with setuptools

### Cap Conditions

- No branch protection evidence (GitHub API check not performed)
- No signed releases / PyPI publishing
- Score 9 would require branch protection + signed releases

### Fixable By

- **Human:** Branch protection configuration, PyPI publishing, signed releases

---

## Dimension 11: Documentation Accuracy (Score: 7)

**Weight: 10% | Prior: 5 | Delta: +2**

### Evidence

- **README.md** (~200 lines): CLI reference with flag tables, output format examples with JSON samples, programmatic API examples, development setup
- QUICKSTART.md, DEPLOYMENT.md present
- **CONTRIBUTING.md** meets Repo Controls §1.2 -- dev setup, test instructions, code style, PR process, issue guidance
- **SECURITY.md** meets Repo Controls §1.1 -- supported versions, reporting, timeline, disclosure, scope
- **CODEBASE_MAP.md** created (Build Standard Phase 0.5)
- **CHANGELOG.md** with version history
- ENHANCEMENTS.md (feature wishlist)
- Module docstrings on all source files (scanner, hashing, signing, text_dedup, reporting, cli)
- Function docstrings with Args/Returns/Raises on all public functions
- `py.typed` marker for PEP 561

### Cap Conditions

- **Capped at 7 per Repository Controls §4.2** -- documentation is hand-maintained with no build validation or link checking in CI
- Score 8 requires doc build validation / link checking in CI

### Fixable By

- **Agent:** Add doc build validation / link checking to CI -> uncap from 7 to 8

---

## Dimension 12: Domain Capability Depth (Score: 7)

**Weight: 8% | Prior: 5 | Delta: +2**

### Evidence
- **Exact duplicate detection:** SHA-256 file hashing, streaming 1MB chunks, duplicate grouping sorted by count
- **Near-duplicate text detection:** MinHash with Jaccard similarity (250 LOC), configurable parameters (num_perm, ngram_size, threshold, seed), Union-Find grouping with path compression
- **Report generation:** Summary statistics (file count, bytes, duplicate groups, unique count, avg file size, largest group)
- **Scan comparison:** Diff between two scans (added/removed/unchanged duplicate groups, file count delta)
- **Integrity signing:** Ed25519 sign/verify for scan results
- **Data provenance:** Tool version, timestamp, root path, filter parameters in every scan
- **Filtering:** Extension filter, max file size, symlink handling

### Cap Conditions
- **No perceptual hashing** (pHash, dHash) for near-duplicate images -- significant gap given "multimodal" name
- No audio/video fingerprinting
- No embedding-based similarity
- No incremental scan / hash caching
- MinHash is text-only; the "multimodal" in the name is aspirational

### Fixable By
- **Agent:** Add perceptual hashing (Pillow + imagehash as optional dep) -> D12 to 8
- **Agent:** Add incremental scan with hash cache -> D12 toward 9

---

## Dimension 13: AI/ML Capability (Score: 4)

**Weight: 5% | Prior: 3 | Delta: +1**

### Evidence
- **MinHash locality-sensitive hashing** -- a probabilistic ML technique for approximate nearest neighbor / similarity estimation
- Configurable parameters: num_perm (accuracy vs speed), ngram_size, threshold, seed
- Mersenne prime universal hash family (2^61 - 1)
- Academic reference in docstring (Broder 1997)

### Cap Conditions
- No embedding computation (no model integration)
- No perceptual hashing (no vision models)
- No dataset statistics / label quality analysis
- No integration with ML data tools (DVC, Great Expectations, HuggingFace datasets)
- MinHash is a classical technique, not modern ML

### Fixable By
- **Agent:** Add optional embedding-based similarity (sentence-transformers or similar) -> D13 to 6
- **Agent:** Add dataset statistics subcommand (class distribution, type analysis) -> D13 to 5

---

## Dimension 14: Connectivity & Channel Interface (Score: 3)

**Weight: 2% | Prior: 2 | Delta: +1**

### Evidence
- CLI-only interface
- JSON file output
- Control-plane ToolSpec definitions for all 4 commands (scan, report, diff, verify) -- enables agent/platform integration
- Input/output schemas defined in tool_specs.py

### Cap Conditions
- No REST API / HTTP server mode
- No webhooks
- No MCP server integration
- Control-plane specs are declared but not runtime-wired

---

## Dimension 18: Zero Trust Architecture (Score: 5)

**Weight: 2% | Prior: 3 | Delta: +2**

### Evidence
- Directory path validation: existence check, is_dir check, path resolution (`validate_directory_path`)
- File input validation: required keys validation in `load_scan_file`
- Max file size limiting (`--max-file-size` flag, `ValueError` on negative)
- Symlink handling option (`--skip-symlinks` to prevent traversal)
- Ed25519 signing for output integrity
- No network calls (no attack surface)
- Input validation on MinHash parameters (threshold 0-1, num_perm >= 1, ngram_size >= 1)

### Cap Conditions
- No resource limits (memory, CPU time, total scan size)
- No process sandboxing
- Default follows symlinks (could escape intended directory boundary)

---

## Dimension 19: Enterprise Security & Compliance (Score: 6)

**Weight: 5% | Prior: 4 | Delta: +2**

### Evidence

- MIT license with proper metadata in pyproject.toml
- CI security scanning: bandit (static analysis) + safety (dependency vulnerabilities)
- Dependabot: automated dependency updates (pip + github-actions)
- Ed25519 report signing for integrity verification
- `.env.example` present (no secrets)
- **SBOM generation in CI** -- CycloneDX via Syft, Grype vulnerability scanning, artifact published
- **SECURITY.md** meets Repository Controls v1.3 §1.1

### Cap Conditions

- No signed commits
- No SLSA alignment
- No audit logging
- Score 7 would require signed commits + SLSA Level 2

### Fixable By

- **Human:** Signed commits (GPG/SSH), SLSA Level 2 alignment, PyPI publishing with provenance

---

## Dimension 20: Operational Readiness (Score: 5)

**Weight: 2% | Prior: 4 | Delta: +1**

### Evidence
- Dockerfile: `python:3.11-slim`, clean install, only git as system dep
- docker-compose.yml with volume mounts for datasets/reports
- `pip install -e .` works cleanly with zero core dependencies
- Entry point registered (`toolkit-mmqa` command)
- `.env.example` for environment configuration

### Cap Conditions
- No production deployment evidence
- No runbook / operations guide
- No PyPI publishing (not `pip install toolkit-multimodal-dataset-qa`)
- No health check endpoint (CLI tool, N/A)

---

## Dimension 21: Agentic Workspace (Score: 5)

**Weight: 2% | Prior: 2 | Delta: +3**

### Evidence
- **Control-plane adapter** (`control_plane/` package, 4 files, ~400 LOC):
  - `contracts.py`: PermissionScope, ApprovalPolicy, AuthorityBoundary, ToolSpec with optional framework import
  - `config.py`: ToolkitConfigContract with 3-tier config hierarchy
  - `tool_specs.py`: 4 ToolSpecs for scan/report/diff/verify, all READ_ONLY + AUTO approval
  - Optional import from `akiva_execution_contracts` / `akiva_policy_runtime` with graceful fallback
- Authority boundaries defined (READ_ONLY scope, AUTO approval)
- Sandbox requirement: None (read-only tool)

### Cap Conditions
- No MCP server integration
- Control-plane is declared, not runtime-wired (no live policy enforcement)
- No agent task execution (standalone CLI)

---

## Standards Checklist

### Core Standards

| Standard | Version | Applicable | Assessment |
|----------|---------|------------|------------|
| Build Standard | v2.14 | Yes | Scored across all 21 dimensions |
| Archetypes | v2.0 | Yes (Arch 9) | Weights applied, minimums checked |
| Sprint Protocol | v3.4 | Yes | SA-1 through SA-13 not formally executed (audit, not sprint) |
| Repository Controls | v1.3 | Yes | SECURITY.md compliant, Issue/PR templates added, SBOM in CI, aggregator job added |
| Operational Standard | v1.4 | Partial | CLI tool, Docker only, no production deployment |
| Pre-Push | v1.2 | Yes | No pre-push workflow configured |

### AI Standards

| Standard | Version | Applicable | Assessment |
|----------|---------|------------|------------|
| AI Response Quality | v1.2 | No | CLI tool, no AI responses |
| AI Service | v1.5 | No | No AI service layer |
| AI Agent Runtime | v1.8 | Partial | Control-plane contracts present (ToolSpec, AuthorityBoundary) |
| AI Resilience | v1.3 | No | No AI-driven behavior |
| Streaming AI Rendering | v1.0 | No | No streaming output |
| RAG & Knowledge Graph | v1.3 | No | No RAG/KG features |
| BENCHMARK | v1.5 | No | No self-improvement loop |

### Domain-Specific Standards

| Standard | Version | Applicable | Assessment |
|----------|---------|------------|------------|
| Integration & Webhook | v1.1 | No | No integrations |
| User Trust | v1.4 | No | CLI tool, no user-facing trust signals |
| Data Isolation | v1.1 | No | Single-user CLI, no multi-tenancy |
| Compliance Framework | v1.0 | Partial | SBOM/SLSA required per Arch 9 certification |
| SBOM & Supply Chain | v1.0 | Yes | No SBOM generation -- gap |
| AI Governance & Ethics | v1.0 | No | No AI models |
| Change Management | v1.0 | No | No change management process |

---

## Top 3 Remaining Gaps (by weighted score impact)

### 1. D11 Documentation Capped at 7 (no doc build validation)

**Impact:** -1.0 weighted point (D11: 7->8 = +1.0)
**Standards:** Repository Controls v1.3 §4.2 -- "Dim 11 can reach 8+ only with automated generation and link checking in CI"
**Current state:** All doc files present (README, CONTRIBUTING, SECURITY, CODEBASE_MAP, CHANGELOG) but no automated link checking or doc build validation in CI.
**Fixable by:** Agent (add link-check step to CI)

### 2. No Perceptual Hashing for Images (D12, D13)

**Impact:** -1.1 weighted points (D12: 7->8 = +0.8, D13: 4->5 = +0.25)
**Standards:** Build Standard v2.14 Dim 12 (Domain Capability Depth)
**Current state:** "Multimodal" name but only text dedup (MinHash) and exact hash dedup. No image-level near-duplicate detection.
**Fixable by:** Agent (add perceptual hashing via imagehash as optional dep)

### 3. Signed Commits + Branch Protection (D8, D19)

**Impact:** -1.5 weighted points (D8: 8->9 = +1.0, D19: 6->7 = +0.5)
**Standards:** Repository Controls v1.3 §10, Archetypes v2.0 (Arch 9: "SBOM / SLSA Level 2: Required")
**Current state:** No GPG/SSH signed commits, no branch protection rules.
**Fixable by:** Human only

---

## Path to 75/100

Current score: 70.5/100. Need +4.5 weighted points.

| Action | Dimensions | Score Change | Weighted | Fixable By |
|--------|-----------|-------------|----------|------------|
| Add doc build validation to CI | D11: 7->8 | +1 | +1.0 | Agent |
| Add perceptual hashing (optional dep) | D12: 7->8, D13: 4->5 | +2 | +1.1 | Agent |
| Add REST API / library server mode | D14: 3->5 | +2 | +0.4 | Agent |
| **Total agent-fixable** | | | **+2.5** | **-> 73.0** |
| Signed commits + branch protection | D8: 8->9, D19: 6->7 | +2 | +1.5 | Human |
| PyPI publishing | D20: 5->6 | +1 | +0.2 | Human |
| **Total with human actions** | | | **+4.2** | **-> 74.7** |

Reaching exactly 75.0 requires closing nearly all remaining gaps including human actions.

---

## Human-Only Blockers

1. **Signed commits** (GPG/SSH signing on protected branches) -- required for SLSA Level 2
2. **Branch protection** on `main` -- status checks required, no force push
3. **PyPI publishing** -- package not available via `pip install`
4. **SLSA Level 2 alignment** -- signed provenance, build service verification
5. **Pen test / security review** -- no evidence of security assessment

---

## Coverage Tracker

| Dimension | Audited | Date |
|-----------|---------|------|
| D1 Architecture | Yes | 2026-04-04 |
| D2 Auth & Identity | Yes | 2026-04-04 |
| D3 Data Isolation | Yes (N/A) | 2026-04-04 |
| D4 API Surface | Yes | 2026-04-04 |
| D5 Data Layer | Yes | 2026-04-04 |
| D6 Frontend | Yes (N/A) | 2026-04-04 |
| D7 Testing | Yes | 2026-04-04 |
| D8 Security | Yes | 2026-04-04 |
| D9 Observability | Yes | 2026-04-04 |
| D10 CI/CD | Yes | 2026-04-04 |
| D11 Documentation | Yes | 2026-04-04 |
| D12 Domain | Yes | 2026-04-04 |
| D13 AI/ML | Yes | 2026-04-04 |
| D14 Connectivity | Yes | 2026-04-04 |
| D15-17 UI/UX | Yes (N/A) | 2026-04-04 |
| D18 Zero Trust | Yes | 2026-04-04 |
| D19 Enterprise Security | Yes | 2026-04-04 |
| D20 Operational | Yes | 2026-04-04 |
| D21 Agentic Workspace | Yes | 2026-04-04 |

## Accepted Exceptions

| Item | Reason |
|------|--------|
| Symlink tests skipped on Windows | Platform limitation; tests exist and pass on Linux CI |
| No user authentication | Archetype 9 CLI tool; D2 weight is 2% |
| No frontend | Archetype 9; D6/D15/D16/D17 weight is 0% |
| No multi-tenancy | Single-user CLI tool; D3 weight is 0% |
| MD5 in MinHash | Non-security-critical (usedforsecurity=False), used for speed |

## Audit Backlog

| Priority | Item | Dimension | Fixable By | Status |
|----------|------|-----------|------------|--------|
| ~~P1~~ | ~~Fix pyright errors + add to CI~~ | D1, D10 | Agent | DONE |
| ~~P1~~ | ~~Expand SECURITY.md to Repo Controls template~~ | D8 | Agent | DONE |
| ~~P1~~ | ~~Add SBOM generation (CycloneDX) to CI~~ | D8, D19 | Agent | DONE |
| ~~P2~~ | ~~Add Issue/PR templates~~ | D10 | Agent | DONE |
| ~~P2~~ | ~~Create CODEBASE_MAP.md~~ | D11 | Agent | DONE |
| ~~P2~~ | ~~Expand CONTRIBUTING.md~~ | D11 | Agent | DONE |
| ~~P2~~ | ~~Add CHANGELOG~~ | D11 | Agent | DONE |
| ~~P2~~ | ~~Add aggregator job to CI~~ | D10 | Agent | DONE |
| P2 | Add perceptual hashing (imagehash optional dep) | D12, D13 | Agent | OPEN |
| P3 | Add doc build validation to CI | D11 | Agent | OPEN |
| P3 | Add REST API / library server mode | D14 | Agent | OPEN |
| P3 | Add dataset statistics subcommand | D13 | Agent | OPEN |
| P3 | Signed commits + branch protection | D8, D19 | Human | OPEN |
| P3 | PyPI publishing with provenance | D19, D20 | Human | OPEN |
| P4 | SLSA Level 2 alignment | D19 | Human | OPEN |
| P4 | Container image scanning | D8 | Agent + Human | OPEN |
