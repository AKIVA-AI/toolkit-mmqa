# Contributing to toolkit-mmqa

## Development Setup

```bash
# Clone and install with dev dependencies
git clone https://github.com/AKIVA-AI/toolkit-mmqa.git
cd toolkit-mmqa
pip install -e ".[dev]"

# For signing features (optional)
pip install -e ".[signing]"
```

## Running Tests

```bash
# Run all tests
pytest -xvs

# Run with coverage
pytest --cov=toolkit_mmqa --cov-report=term-missing

# Run a specific test file
pytest tests/test_scan.py -v
```

## Code Style and Linting

```bash
# Lint
ruff check src/ tests/

# Type check
pyright src/
```

- Line length: 100 characters
- Ruff rules: E, F, I, B, UP
- Target Python: 3.10+

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for new functionality before implementation
3. Ensure all checks pass: `pytest`, `ruff check`, `pyright`
4. Keep core hashing logic dependency-free (optional deps go in `[project.optional-dependencies]`)
5. Add tests for new report fields or CLI flags
6. Update README.md if adding new CLI commands or flags
7. Open a PR with a clear description of what changed and why

## Issue Reporting

- Use the bug report template for bugs (include reproduction steps)
- Use the feature request template for new capabilities
- Include the toolkit version (`toolkit-mmqa --version`)
