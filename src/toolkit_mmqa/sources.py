"""Record sources: local files or Hugging Face Hub datasets.

A source spec is either a path (``train.jsonl``) or a Hub dataset::

    hf:NAME:SPLIT
    hf:NAME:CONFIG:SPLIT
    hf:NAME:CONFIG:SPLIT@REVISION

for example ``hf:openai/gsm8k:main:test``. Hub datasets need the optional
``[hf]`` extra (the ``datasets`` library) and are streamed, so nothing is
written to the datasets cache for the records themselves.

Every source can describe itself as an in-toto resource descriptor for the
report. For a file this is its SHA-256. A Hub dataset has no single file, so
its digest is the SHA-256 of the records as read: one canonical JSON line
``{"id": ..., "index": ..., "text": ...}`` per record, in order. Pin a
``@REVISION`` to make that digest reproducible.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .envelope import file_descriptor
from .records import Record, RecordError, _record_from, iter_records

HF_PREFIX = "hf:"
_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class HubSpec:
    dataset: str
    config: str | None
    split: str
    revision: str | None


def parse_hf_spec(spec: str) -> HubSpec:
    """Parse ``hf:NAME[:CONFIG]:SPLIT[@REVISION]``.

    Raises:
        ValueError: If the spec does not have 2 or 3 non-empty parts.
    """
    if not spec.startswith(HF_PREFIX):
        raise ValueError(f"not a Hub spec: {spec!r}")
    body, _, revision = spec[len(HF_PREFIX) :].partition("@")
    parts = body.split(":")
    if len(parts) not in (2, 3) or not all(parts):
        raise ValueError(f"expected hf:NAME[:CONFIG]:SPLIT[@REVISION], got {spec!r}")
    config = parts[1] if len(parts) == 3 else None
    return HubSpec(dataset=parts[0], config=config, split=parts[-1], revision=revision or None)


def _load_hub(spec: HubSpec) -> Any:
    try:
        import datasets
    except ImportError as e:
        raise ValueError(
            "Hub datasets need the [hf] extra: pip install 'toolkit-mmqa[hf]'"
        ) from e
    return datasets.load_dataset(
        spec.dataset, spec.config, split=spec.split, revision=spec.revision, streaming=True
    )


@dataclass
class Source:
    """A named source of records (a file or a Hub dataset split)."""

    name: str
    spec: str
    path: Path | None = None
    hub: HubSpec | None = None
    _digest: Any = field(default=None, repr=False)
    _read: int = 0

    @property
    def is_file(self) -> bool:
        return self.path is not None

    def check(self) -> None:
        """Fail early on a missing file (Hub sources are checked when read)."""
        if self.path is not None and not self.path.is_file():
            raise FileNotFoundError(f"File not found: {self.path}")

    def iter_records(self, *, fields: Sequence[str], id_field: str | None) -> Iterator[Record]:
        if self.path is not None:
            yield from iter_records(self.path, fields=fields, id_field=id_field)
            return
        if self.hub is None:  # pragma: no cover - constructor guarantees one of both
            raise RuntimeError("source has neither a path nor a Hub spec")
        if not fields:
            raise RecordError("at least one text field is required")
        self._digest = hashlib.sha256()
        self._read = 0
        for index, row in enumerate(_load_hub(self.hub)):
            rec = _record_from(
                row, index=index, fields=fields, id_field=id_field, where=f"{self.spec}[{index}]"
            )
            line = json.dumps(
                {"id": rec.id, "index": rec.index, "text": rec.text},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            self._digest.update(line.encode("utf-8") + b"\n")
            self._read += 1
            yield rec

    def load(self, *, fields: Sequence[str], id_field: str | None) -> list[Record]:
        return list(self.iter_records(fields=fields, id_field=id_field))

    def descriptor(self) -> dict[str, Any]:
        """Resource descriptor for the report (read Hub sources first)."""
        if self.path is not None:
            return file_descriptor(self.path, name=self.name)
        if self.hub is None:  # pragma: no cover
            raise RuntimeError("source has neither a path nor a Hub spec")
        digest = self._digest.hexdigest() if self._digest is not None else None
        if digest is None:
            digest = hashlib.sha256(b"").hexdigest()
        annotations: dict[str, Any] = {"split": self.hub.split, "records_read": self._read}
        if self.hub.config:
            annotations["config"] = self.hub.config
        if self.hub.revision:
            annotations["revision"] = self.hub.revision
        return {
            "name": self.name,
            "uri": f"hf://datasets/{self.hub.dataset}",
            "digest": {"sha256": digest},
            "annotations": annotations,
        }


def parse_source(raw: str) -> Source:
    """Parse ``[NAME=]PATH`` or ``[NAME=]hf:...`` into a :class:`Source`."""
    name, sep, rest = raw.partition("=")
    if sep and _NAME_RE.fullmatch(name) and rest:
        spec = rest
    else:
        name, spec = "", raw
    if spec.startswith(HF_PREFIX):
        hub = parse_hf_spec(spec)
        return Source(name=name or spec[len(HF_PREFIX) :], spec=spec, hub=hub)
    path = Path(spec)
    return Source(name=name or path.name, spec=spec, path=path)
