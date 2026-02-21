# Toolkit Multimodal Dataset QA (Enterprise Tool)

Quick dataset QA utilities:

- scan a directory tree
- compute file hashes
- detect exact duplicates

The core is dependency-free (works for any file types). Higher-order similarity (pHash/embeddings) can be added later as
optional extras.

## Install

```bash
pip install -e ".[dev]"
```

## Scan + dedupe report

```bash
toolkit-mmqa scan --root ./dataset --out report.json
```



