# MMQA — Multi-modal dataset scanning, hashing, and change tracking

**Archetype:** 9 — Developer Tool / CLI Utility
**Standards:** Akiva Build Standard v2.14
**Ontology ID:** TK-08

## Stack

- Language: Python 3.10+
- Test: `pytest -xvs`
- Lint: `ruff check src/ tests/`
- Type check: `pyright src/`
- Build: `pip install -e .`

## Verification Commands

| Command                    | Purpose    |
|----------------------------|------------|
| `pytest -xvs`             | Run tests  |
| `ruff check src/ tests/`  | Lint       |
| `pyright src/`             | Type check |

## Current State

- Audit Score: 70.5/100 (2026-04-04, v2.14 baseline)
- Prior Audit: 56.3/100 (2026-03-09)
- Tests: 229 (86.79% coverage)
- Pyright: 0 errors (control_plane excluded per CI pattern; 7 warnings for optional cryptography)

## Key Rules

- Archetype 9: single-purpose CLI tool, zero or minimal dependencies in core
- Tests first, security fixes before features
- One task at a time, verified before moving to next
