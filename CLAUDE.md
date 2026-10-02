# toolkit-mmqa: guidance for coding agents

Dataset pre-flight QA: train/eval and benchmark contamination, record-level
dedup, file-level duplicates / manifest / diff, image and audio checks. Every
command writes a report envelope (in-toto Statement v1, canonical JSON; spec in
`docs/report-envelope.md`). Layout and module graph: `docs/CODEBASE_MAP.md`.

## Commands

| Purpose | Command |
|---|---|
| Install (dev) | `pip install -e ".[dev]"` |
| Tests | `pytest -q` |
| Core-only tests | `pip install -e . pytest && pytest -q` |
| Lint | `ruff check src/ tests/` |
| Type check | `pyright src/` |

## Conventions

- The core package has no runtime dependencies. Optional features go behind
  an extra in `pyproject.toml` (e.g. `[signing]` for `cryptography`).
- The version lives only in `src/toolkit_mmqa/_version.py`.
- Tests first: add a failing test, then the fix. Tests should exercise behavior
  (real files in `tmp_path`, real CLI calls via `toolkit_mmqa.cli.main`).
- The scan JSON is a public format. Changing a field is a breaking change:
  update README "Output formats" and CHANGELOG in the same PR.
- LSH banding in `text_dedup._choose_bands` must keep `bands > max mismatches`
  so LSH never misses a pair the exhaustive comparison would accept.
- Keep README's capability table honest (Working / Partial / Planned).
- Heavy integrations are optional extras imported lazily (e.g. Pillow for
  `[image]`); the core must import and run with no third-party packages.
- Every new statistic is tested against a reference implementation or a
  published worked example, cited in the test docstring (e.g. image hashes vs
  `imagehash`, n-gram overlap vs a brute-force implementation).
