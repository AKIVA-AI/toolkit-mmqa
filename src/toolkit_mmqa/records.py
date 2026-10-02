"""Read text records from dataset files (JSONL, JSON, CSV, plain text).

A *record* is one training or evaluation example. Its text is taken from one or
more fields; several fields are joined with a newline. Reading is fail-closed:
a malformed line or a missing field raises :class:`RecordError` with the file
and line, instead of silently skipping the record.

Supported inputs:

* ``.jsonl`` / ``.ndjson``: one JSON object (or string) per line.
* ``.json``: a JSON array of objects or strings.
* ``.csv``: header row, one record per row.
* ``.txt`` and anything else: one record per non-empty line.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_FIELDS = ("text",)


class RecordError(ValueError):
    """A record could not be read (malformed input or missing field)."""


@dataclass(frozen=True)
class Record:
    """One example.

    Attributes:
        index: 0-based position of the record in its source.
        text: The record text (selected fields joined with a newline).
        id: Value of the id field, if one was requested and present.
    """

    index: int
    text: str
    id: str | None = None


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_value_text(v) for v in value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _record_from(
    obj: Any,
    *,
    index: int,
    fields: Sequence[str],
    id_field: str | None,
    where: str,
) -> Record:
    if isinstance(obj, str):
        return Record(index=index, text=obj)
    if not isinstance(obj, dict):
        raise RecordError(f"{where}: expected a JSON object or string, got {type(obj).__name__}")
    parts = []
    for f in fields:
        if f not in obj:
            available = ", ".join(sorted(map(str, obj))[:10])
            raise RecordError(f"{where}: missing field {f!r} (available: {available})")
        parts.append(_value_text(obj[f]))
    rid = None
    if id_field is not None and obj.get(id_field) is not None:
        rid = _value_text(obj[id_field])
    return Record(index=index, text="\n".join(parts), id=rid)


def iter_records(
    path: Path,
    *,
    fields: Sequence[str] = DEFAULT_FIELDS,
    id_field: str | None = None,
) -> Iterator[Record]:
    """Yield the records of *path* one at a time (JSONL, CSV and text stream).

    Raises:
        RecordError: On a malformed line or a missing field.
        FileNotFoundError: If *path* does not exist.
    """
    if not fields:
        raise RecordError("at least one text field is required")
    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        with path.open(encoding="utf-8-sig") as f:
            index = 0
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                where = f"{path.name}:{lineno}"
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise RecordError(f"{where}: invalid JSON ({e.msg})") from e
                yield _record_from(obj, index=index, fields=fields, id_field=id_field, where=where)
                index += 1
    elif suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise RecordError(f"{path.name}: invalid JSON ({e.msg})") from e
        if not isinstance(data, list):
            raise RecordError(f"{path.name}: expected a JSON array of records")
        for index, obj in enumerate(data):
            where = f"{path.name}[{index}]"
            yield _record_from(obj, index=index, fields=fields, id_field=id_field, where=where)
    elif suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for index, row in enumerate(reader):
                where = f"{path.name}:{index + 2}"
                yield _record_from(row, index=index, fields=fields, id_field=id_field, where=where)
    else:
        with path.open(encoding="utf-8-sig") as f:
            index = 0
            for line in f:
                text = line.rstrip("\r\n")
                if not text.strip():
                    continue
                yield Record(index=index, text=text)
                index += 1


def load_records(
    path: Path,
    *,
    fields: Sequence[str] = DEFAULT_FIELDS,
    id_field: str | None = None,
) -> list[Record]:
    """Read all records of *path* into a list. See :func:`iter_records`."""
    return list(iter_records(path, fields=fields, id_field=id_field))


def write_without(path: Path, drop: set[int], out: Path) -> int:
    """Copy the line-based file *path* to *out*, leaving out records in *drop*.

    Record indexes count non-blank lines, as :func:`iter_records` does, and kept
    lines are copied byte for byte. Only JSONL/NDJSON and text files are
    supported.

    Returns:
        The number of records written.

    Raises:
        ValueError: For JSON arrays, CSV or other formats.
    """
    if path.suffix.lower() in (".json", ".csv"):
        raise ValueError(
            f"writing a deduplicated copy supports JSONL and text files, not {path.suffix}"
        )
    written = 0
    index = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with path.open("rb") as src, out.open("wb") as dst:
        for line in src:
            # Same blank-line rule as iter_records (str.strip, BOM ignored).
            if not line.decode("utf-8", errors="replace").lstrip("﻿").strip():
                continue
            if index not in drop:
                dst.write(line if line.endswith(b"\n") else line + b"\n")
                written += 1
            index += 1
    return written


def parse_fields(raw: str | None) -> tuple[str, ...]:
    """Parse a comma-separated ``--field`` value (default ``text``)."""
    if raw is None or not raw.strip():
        return DEFAULT_FIELDS
    return tuple(f.strip() for f in raw.split(",") if f.strip())
