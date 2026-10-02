"""Report envelope v1: every machine-readable report is an in-toto Statement v1.

The shape is shared by the toolkit family (see ``docs/report-envelope.md`` and
``schemas/report-envelope.v1.json``)::

    {
      "_type": "https://in-toto.io/Statement/v1",
      "subject": [{"name": ..., "digest": {"sha256": ...}}],
      "predicateType": "https://github.com/AKIVA-AI/toolkit-mmqa/report/v1",
      "predicate": {
        "tool": {"name": "toolkit-mmqa", "version": ...},
        "kind": "mmqa.scan", "created_at": "2026-09-26T18:00:00Z",
        "verdict": "pass" | "fail" | "error", "exit_code": 0,
        "inputs": [...], "summary": {...}, "details": {...}
      }
    }

Reports are written as canonical JSON (UTF-8, sorted keys, no insignificant
whitespace, trailing newline) so the SHA-256 of a report file is stable and
the file can be signed and verified with standard tooling.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._version import __version__

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
TOOL_NAME = "toolkit-mmqa"
PREDICATE_TYPE = f"https://github.com/AKIVA-AI/{TOOL_NAME}/report/v1"

VERDICT_PASS = "pass"  # nosec B105 - verdict label, not a password
VERDICT_FAIL = "fail"
VERDICT_ERROR = "error"

#: Exit code for each verdict. ``error`` covers every exit code >= 2.
VERDICT_EXIT_CODES = {VERDICT_PASS: 0, VERDICT_FAIL: 1, VERDICT_ERROR: 2}


def canonical_bytes(obj: Any) -> bytes:
    """Canonical JSON: UTF-8, sorted keys, compact separators, trailing newline."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_descriptor(path: Path, name: str | None = None) -> dict[str, Any]:
    """Resource descriptor ``{"name", "digest": {"sha256"}}`` for a file on disk."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {"name": name if name is not None else str(path), "digest": {"sha256": h.hexdigest()}}


def manifest_digest(files: dict[str, dict[str, Any]]) -> str:
    """Digest of a dataset manifest.

    SHA-256 of the canonical JSON (sorted keys, no whitespace, no trailing
    newline) of the object ``{relative_path: sha256}``. Anyone holding the
    same files can recompute it, so it identifies the dataset's contents.
    """
    mapping = {path: str(entry["sha256"]) for path, entry in files.items()}
    text = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_hex(text.encode("utf-8"))


def utc_now() -> str:
    """RFC 3339 UTC timestamp with a ``Z`` suffix, second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_envelope(
    *,
    kind: str,
    subject: list[dict[str, Any]],
    verdict: str,
    exit_code: int,
    summary: dict[str, Any],
    details: dict[str, Any],
    inputs: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a report envelope and check that verdict and exit code agree.

    Raises:
        ValueError: If the verdict is unknown, disagrees with ``exit_code``, or
            ``subject`` is empty.
    """
    if verdict not in VERDICT_EXIT_CODES:
        raise ValueError(f"unknown verdict: {verdict!r}")
    if verdict == VERDICT_ERROR:
        if exit_code < 2:
            raise ValueError(f"verdict 'error' needs exit code >= 2, got {exit_code}")
    elif exit_code != VERDICT_EXIT_CODES[verdict]:
        raise ValueError(
            f"verdict {verdict!r} needs exit code {VERDICT_EXIT_CODES[verdict]}, got {exit_code}"
        )
    if not subject:
        raise ValueError("an envelope needs at least one subject")
    return {
        "_type": STATEMENT_TYPE,
        "subject": subject,
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "tool": {"name": TOOL_NAME, "version": __version__},
            "kind": kind,
            "created_at": created_at or utc_now(),
            "verdict": verdict,
            "exit_code": int(exit_code),
            "inputs": list(inputs or []),
            "summary": summary,
            "details": details,
        },
    }


def is_envelope(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("_type") == STATEMENT_TYPE


def unwrap(obj: dict[str, Any], expected_kind: str) -> dict[str, Any]:
    """Return ``predicate.details`` of an envelope of ``expected_kind``.

    Raises:
        ValueError: If ``obj`` is an envelope from another tool or of another kind.
    """
    if obj.get("predicateType") != PREDICATE_TYPE:
        raise ValueError(f"not a {TOOL_NAME} report: predicateType={obj.get('predicateType')!r}")
    predicate = obj.get("predicate")
    if not isinstance(predicate, dict):
        raise ValueError("report has no predicate object")
    kind = predicate.get("kind")
    if kind != expected_kind:
        raise ValueError(f"expected a {expected_kind!r} report, got {kind!r}")
    details = predicate.get("details")
    if not isinstance(details, dict):
        raise ValueError("report has no details object")
    return details


def write_report(obj: dict[str, Any], out: Path) -> bytes:
    """Write ``obj`` as canonical JSON to ``out``; return the bytes written."""
    data = canonical_bytes(obj)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return data


def render_markdown(envelope: dict[str, Any], extra: list[str] | None = None) -> str:
    """Human-readable summary of an envelope (not a stable format).

    ``extra`` lines (for example a table of flagged items) are appended.
    """
    pred = envelope["predicate"]
    lines = [
        f"# {pred['tool']['name']} {pred['kind']}",
        "",
        f"Verdict: **{pred['verdict']}** (exit code {pred['exit_code']})",
        "",
        "Subject: "
        + ", ".join(
            f"`{s['name']}` (sha256 {s['digest']['sha256'][:12]})" for s in envelope["subject"]
        ),
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key in sorted(pred["summary"]):
        value = pred["summary"][key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True)
        lines.append(f"| {key} | {value} |")
    if extra:
        lines.append("")
        lines.extend(extra)
    return "\n".join(lines) + "\n"
