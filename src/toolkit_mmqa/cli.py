from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .audio import check_audio
from .contamination import (
    DEFAULT_MIN_NGRAM_SIZE,
    DEFAULT_MINHASH_THRESHOLD,
    DEFAULT_NGRAM_SIZE,
    METHODS,
    ContaminationResult,
    Target,
    check_contamination,
)
from .dedup import SourceRecords, dedup_records
from .envelope import (
    VERDICT_ERROR,
    VERDICT_FAIL,
    VERDICT_PASS,
    build_envelope,
    canonical_bytes,
    file_descriptor,
    manifest_digest,
    render_markdown,
)
from .images import DEFAULT_MAX_DISTANCE, _require_pillow, check_images
from .records import RecordError, parse_fields, write_without
from .reporting import SCAN_KIND, diff_scans, generate_report, load_scan_file, scan_subject
from .scanner import scan
from .sources import parse_source
from .text_dedup import find_near_duplicates, load_text_files

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_GATE_FAILED = 1
EXIT_CLI_ERROR = 2
EXIT_UNEXPECTED_ERROR = 3

DEFAULT_NEAR_DUP_THRESHOLD = 0.8

FORMAT_JSON = "json"
FORMAT_LEGACY = "legacy-json"
FORMAT_MARKDOWN = "markdown"

RECORD_CHECKS = ("exact-duplicates", "near-duplicates")
SCAN_CHECKS = ("exact-duplicates", "near-duplicates", "corrupt-media", "image-near-duplicates")
CONTAMINATION_KIND = "mmqa.contamination"
DEDUP_KIND = "mmqa.dedup"


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def validate_directory_path(path: Path) -> Path:
    """Validate directory path exists and is readable.

    Args:
        path: Path to validate

    Returns:
        Resolved absolute path

    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If path is not a directory
    """
    resolved = path.resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Directory not found: {resolved}")

    if not resolved.is_dir():
        raise ValueError(f"Path is not a directory: {resolved}")

    return resolved


def _parse_checks(raw: str, allowed: tuple[str, ...], flag: str = "--fail-on") -> list[str]:
    checks = [c.strip() for c in raw.split(",") if c.strip()]
    unknown = sorted(set(checks) - set(allowed))
    if unknown:
        raise ValueError(f"{flag}: unknown value(s) {unknown}; choose from {list(allowed)}")
    return sorted(set(checks))


def _write_output(args: argparse.Namespace, text: str) -> bytes | None:
    """Write *text* to ``--out`` (returning the bytes written) or to stdout."""
    if args.out:
        out_path = Path(args.out).resolve()
        data = text.encode("utf-8")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        logger.info(f"Report saved to: {out_path}")
        return data
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    return None


def _emit(
    args: argparse.Namespace,
    envelope: dict[str, Any],
    legacy: dict[str, Any] | None = None,
    markdown_extra: list[str] | None = None,
) -> int:
    """Write a report in the requested ``--format``; return its exit code."""
    fmt = getattr(args, "format", FORMAT_JSON)
    if fmt == FORMAT_MARKDOWN:
        _write_output(args, render_markdown(envelope, markdown_extra))
    elif fmt == FORMAT_LEGACY and legacy is not None:
        _write_output(args, json.dumps(legacy, indent=2, sort_keys=True))
    else:
        _write_output(args, canonical_bytes(envelope).decode("utf-8"))
    return int(envelope["predicate"]["exit_code"])


def _load_private_key(args: argparse.Namespace) -> str:
    key_path = Path(args.sign_key).resolve()
    if not key_path.exists():
        raise FileNotFoundError(f"Signing key not found: {key_path}")
    from .signing import _ensure_cryptography

    try:
        _ensure_cryptography()
    except RuntimeError as e:
        raise ValueError(str(e)) from e
    return key_path.read_text(encoding="utf-8")


def _cmd_scan(args: argparse.Namespace) -> int:
    """Scan directory for duplicate files."""
    near_dup = getattr(args, "near_dup_text", False)
    near_dup_threshold = getattr(args, "near_dup_threshold", None)
    if near_dup_threshold is not None and not near_dup:
        raise ValueError("--near-dup-threshold requires --near-dup-text")
    if near_dup_threshold is None:
        near_dup_threshold = DEFAULT_NEAR_DUP_THRESHOLD
    if not 0.0 <= near_dup_threshold <= 1.0:
        raise ValueError(f"--near-dup-threshold must be in [0, 1], got {near_dup_threshold}")

    fail_on = _parse_checks(getattr(args, "fail_on", "") or "", SCAN_CHECKS)
    if "near-duplicates" in fail_on and not near_dup:
        raise ValueError("--fail-on near-duplicates requires --near-dup-text")
    image_checks = getattr(args, "image_checks", False)
    if "image-near-duplicates" in fail_on and not image_checks:
        raise ValueError("--fail-on image-near-duplicates requires --image-checks")
    audio_checks = getattr(args, "audio_checks", False)
    if "corrupt-media" in fail_on and not (image_checks or audio_checks):
        raise ValueError("--fail-on corrupt-media requires --image-checks or --audio-checks")
    image_distance = getattr(args, "image_hash_distance", DEFAULT_MAX_DISTANCE)
    if not 0 <= image_distance <= 64:
        raise ValueError(f"--image-hash-distance must be in [0, 64], got {image_distance}")
    if image_checks:
        try:
            _require_pillow()
        except RuntimeError as e:
            raise ValueError(str(e)) from e

    fmt = getattr(args, "format", FORMAT_JSON)
    signing = getattr(args, "sign", False)
    if signing and fmt == FORMAT_MARKDOWN:
        raise ValueError("--sign needs --format json or legacy-json")
    if signing and fmt == FORMAT_JSON and not args.out:
        raise ValueError("--sign with the report envelope needs --out (the signature is <out>.sig)")
    private_key_pem = _load_private_key(args) if signing else None

    root_path = validate_directory_path(Path(args.root))
    logger.info(f"Scanning directory: {root_path}")

    exts = None
    if args.extensions:
        exts = {x.strip().lower().lstrip(".") for x in str(args.extensions).split(",") if x.strip()}
        logger.info(f"Filtering extensions: {', '.join(sorted(exts))}")

    result = scan(
        root=root_path,
        extensions=exts,
        max_file_size=getattr(args, "max_file_size", None),
        follow_symlinks=getattr(args, "follow_symlinks", False),
        progress=getattr(args, "progress", False),
        workers=getattr(args, "workers", 1),
    )
    logger.info(
        f"Scan complete: {result.file_count} files, "
        f"{len(result.duplicates)} duplicate groups, "
        f"{result.total_bytes:,} bytes"
    )

    details = result.to_json()
    report = generate_report(details)
    summary: dict[str, Any] = {
        "file_count": result.file_count,
        "total_bytes": result.total_bytes,
        "duplicate_group_count": report.duplicate_group_count,
        "duplicate_file_count": report.duplicate_file_count,
        "unique_content_count": report.unique_content_count,
        "skipped_files": result.skipped_count
        + result.skipped_oversized
        + result.skipped_symlinks,
    }
    failed: list[str] = []
    if "exact-duplicates" in fail_on and result.duplicates:
        failed.append("exact-duplicates")

    if near_dup:
        texts, skipped_non_text = load_text_files(root_path, result.files)
        nd = find_near_duplicates(texts, threshold=near_dup_threshold)
        details["near_duplicates"] = {
            "threshold": near_dup_threshold,
            "text_file_count": len(texts),
            "skipped_non_text": skipped_non_text,
            "groups": nd.near_duplicate_groups,
            "similarity_scores": nd.similarity_scores,
        }
        summary["near_duplicate_group_count"] = len(nd.near_duplicate_groups)
        if "near-duplicates" in fail_on and nd.near_duplicate_groups:
            failed.append("near-duplicates")
        logger.info(
            f"Near-duplicate text: {len(nd.near_duplicate_groups)} groups "
            f"among {len(texts)} text files (threshold {near_dup_threshold})"
        )

    corrupt_count = 0
    if image_checks:
        images = check_images(root_path, result.files, max_distance=image_distance)
        details["images"] = images.to_json()
        corrupt_count += len(images.corrupt)
        summary["image_count"] = images.checked_count
        summary["image_near_duplicate_group_count"] = len(images.near_duplicate_groups)
        if "image-near-duplicates" in fail_on and images.near_duplicate_groups:
            failed.append("image-near-duplicates")
        logger.info(
            f"Images: {images.checked_count} checked, {len(images.corrupt)} corrupt, "
            f"{len(images.near_duplicate_groups)} near-duplicate groups"
        )
    if audio_checks:
        audio = check_audio(root_path, result.files)
        details["audio"] = audio.to_json()
        corrupt_count += len(audio.corrupt)
        summary["audio_count"] = audio.checked_count
        summary["audio_unsupported_count"] = len(audio.unsupported)
        summary["audio_total_seconds"] = details["audio"]["duration"].get("total_seconds", 0.0)
        logger.info(
            f"Audio: {audio.checked_count} checked, {len(audio.corrupt)} corrupt, "
            f"{len(audio.unsupported)} unsupported"
        )
    if image_checks or audio_checks:
        summary["corrupt_media_count"] = corrupt_count
        if "corrupt-media" in fail_on and corrupt_count:
            failed.append("corrupt-media")

    summary["fail_on"] = fail_on
    summary["failed_checks"] = sorted(failed)
    verdict = VERDICT_FAIL if failed else VERDICT_PASS
    envelope = build_envelope(
        kind=SCAN_KIND,
        subject=[
            {
                "name": root_path.name or str(root_path),
                "digest": {"sha256": manifest_digest(result.files)},
            }
        ],
        verdict=verdict,
        exit_code=EXIT_GATE_FAILED if failed else EXIT_SUCCESS,
        summary=summary,
        details=details,
    )

    if private_key_pem is None:
        return _emit(args, envelope, details)

    from .signing import canonical_json_bytes, sign_payload

    if fmt == FORMAT_LEGACY:
        details["signature"] = sign_payload(
            payload=canonical_json_bytes(details), private_key_pem=private_key_pem
        )
        logger.info("Scan result signed with Ed25519 key (embedded signature)")
        return _emit(args, envelope, details)

    # Sign the exact bytes before writing anything, so a bad key leaves no
    # unsigned report behind.
    data = canonical_bytes(envelope)
    signature = sign_payload(payload=data, private_key_pem=private_key_pem)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    sig_path = out_path.with_name(out_path.name + ".sig")
    sig_path.write_text(signature + "\n", encoding="ascii")
    logger.info(f"Report saved to {out_path}; detached Ed25519 signature: {sig_path}")
    return int(envelope["predicate"]["exit_code"])


def _cmd_report(args: argparse.Namespace) -> int:
    """Generate summary report from a scan result file."""
    scan_path = Path(args.input).resolve()
    if not scan_path.exists():
        raise FileNotFoundError(f"Scan file not found: {scan_path}")

    data = load_scan_file(scan_path)
    summary = generate_report(data).to_json()
    envelope = build_envelope(
        kind="mmqa.report",
        subject=scan_subject(scan_path),
        verdict=VERDICT_PASS,
        exit_code=EXIT_SUCCESS,
        inputs=[file_descriptor(scan_path, name=scan_path.name)],
        summary=summary,
        details={},
    )
    return _emit(args, envelope, summary)


def _cmd_diff(args: argparse.Namespace) -> int:
    """Compare two scan result files."""
    old_path = Path(args.old).resolve()
    new_path = Path(args.new).resolve()

    for label, p in [("Old", old_path), ("New", new_path)]:
        if not p.exists():
            raise FileNotFoundError(f"{label} scan file not found: {p}")

    result = diff_scans(load_scan_file(old_path), load_scan_file(new_path))
    details = result.to_json()
    summary = {
        "added_file_count": len(result.added_files),
        "removed_file_count": len(result.removed_files),
        "modified_file_count": len(result.modified_files),
        "unchanged_file_count": result.unchanged_file_count,
        "added_duplicate_group_count": len(result.added_duplicate_groups),
        "removed_duplicate_group_count": len(result.removed_duplicate_groups),
    }
    envelope = build_envelope(
        kind="mmqa.diff",
        subject=scan_subject(new_path),
        verdict=VERDICT_PASS,
        exit_code=EXIT_SUCCESS,
        inputs=[
            file_descriptor(old_path, name=old_path.name),
            file_descriptor(new_path, name=new_path.name),
        ],
        summary=summary,
        details=details,
    )
    return _emit(args, envelope, details)


def _error_report(
    args: argparse.Namespace,
    *,
    kind: str,
    subject: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    error: str,
) -> int:
    """Log *error* and, when writing JSON to ``--out``, write an ``error`` report."""
    logger.error(error)
    if args.out and getattr(args, "format", FORMAT_JSON) == FORMAT_JSON and subject:
        envelope = build_envelope(
            kind=kind,
            subject=subject,
            verdict=VERDICT_ERROR,
            exit_code=EXIT_CLI_ERROR,
            inputs=inputs,
            summary={"error": error},
            details={"error": error},
        )
        _write_output(args, canonical_bytes(envelope).decode("utf-8"))
    return EXIT_CLI_ERROR


def _contamination_markdown(result: ContaminationResult, limit: int = 20) -> list[str]:
    lines = [
        "| Target | Records | Contaminated | Fraction |",
        "|---|---|---|---|",
    ]
    for t in result.targets:
        lines.append(
            f"| {t['name']} | {t['record_count']} | {t['contaminated_count']} "
            f"| {t['contaminated_fraction']:.4f} |"
        )
    if result.records:
        lines += ["", "| Target | Index | Methods | Preview |", "|---|---|---|---|"]
        for r in result.records[:limit]:
            preview = " ".join(r["preview"].split())[:80].replace("|", "/")
            lines.append(f"| {r['target']} | {r['index']} | {','.join(r['methods'])} | {preview} |")
        if len(result.records) > limit:
            lines.append(f"\n{len(result.records) - limit} more in the JSON report.")
    return lines


def _cmd_contamination(args: argparse.Namespace) -> int:
    """Check evaluation splits and benchmarks against training data."""
    methods = _parse_checks(args.methods, METHODS, flag="--methods")
    if not methods:
        raise ValueError("--methods needs at least one method")
    if not 0.0 <= args.max_contamination <= 1.0:
        raise ValueError(f"--max-contamination must be in [0, 1], got {args.max_contamination}")
    base_fields = parse_fields(args.field)
    train_fields = parse_fields(args.train_field) if args.train_field else base_fields
    eval_fields = parse_fields(args.eval_field) if args.eval_field else base_fields

    target_specs = [(parse_source(t), "eval") for t in args.eval or []]
    target_specs += [(parse_source(t), "benchmark") for t in args.benchmark or []]
    if not target_specs:
        raise ValueError("give at least one --eval or --benchmark source")
    train_sources = [parse_source(t) for t in args.train]
    names = [src.name for src, _ in target_specs]
    if len(set(names)) != len(names):
        raise ValueError(f"target names must be unique, got {names}; use NAME=PATH")
    for src in train_sources + [src for src, _ in target_specs]:
        src.check()

    def subject() -> list[dict[str, Any]]:
        return [src.descriptor() for src, _ in target_specs]

    def inputs() -> list[dict[str, Any]]:
        return [src.descriptor() for src in train_sources]

    try:
        targets = [
            Target(
                name=src.name,
                role=role,
                records=src.load(fields=eval_fields, id_field=args.id_field),
            )
            for src, role in target_specs
        ]
        result = check_contamination(
            (
                (src.name, src.iter_records(fields=train_fields, id_field=args.id_field))
                for src in train_sources
            ),
            targets,
            methods=methods,
            ngram_size=args.ngram_size,
            min_ngram_size=args.min_ngram_size,
            ngram_threshold=args.ngram_threshold,
            minhash_threshold=args.minhash_threshold,
            max_train_matches=args.max_train_matches,
        )
    except (RecordError, UnicodeDecodeError) as e:
        return _error_report(
            args, kind=CONTAMINATION_KIND, subject=subject(), inputs=inputs(), error=str(e)
        )

    failed = result.failed_targets(args.max_contamination)
    eval_count = sum(t["record_count"] for t in result.targets)
    contaminated = sum(t["contaminated_count"] for t in result.targets)
    summary: dict[str, Any] = {
        "train_record_count": sum(result.train_record_count.values()),
        "eval_record_count": eval_count,
        "contaminated_count": contaminated,
        "contaminated_fraction": {
            t["name"]: t["contaminated_fraction"] for t in result.targets
        },
        "max_contamination": args.max_contamination,
        "failed_targets": failed,
        "methods": list(methods),
    }
    envelope = build_envelope(
        kind=CONTAMINATION_KIND,
        subject=subject(),
        verdict=VERDICT_FAIL if failed else VERDICT_PASS,
        exit_code=EXIT_GATE_FAILED if failed else EXIT_SUCCESS,
        inputs=inputs(),
        summary=summary,
        details={
            "parameters": result.parameters,
            "train": [
                {"name": n, "record_count": c} for n, c in result.train_record_count.items()
            ],
            "targets": result.targets,
            "contaminated_records": result.records,
        },
    )
    logger.info(
        f"Contamination: {contaminated} of {eval_count} evaluation records found in training data"
    )
    return _emit(args, envelope, markdown_extra=_contamination_markdown(result))


def _cmd_dedup(args: argparse.Namespace) -> int:
    """Find duplicate and near-duplicate records in text datasets."""
    fail_on = _parse_checks(args.fail_on or "", RECORD_CHECKS)
    if "near-duplicates" in fail_on and not args.near_dup:
        raise ValueError("--fail-on near-duplicates requires --near-dup")
    if not 0.0 <= args.near_dup_threshold <= 1.0:
        raise ValueError(f"--near-dup-threshold must be in [0, 1], got {args.near_dup_threshold}")
    specs = [parse_source(p) for p in args.input]
    names = [src.name for src in specs]
    if len(set(names)) != len(names):
        raise ValueError(f"input names must be unique, got {names}; use NAME=PATH")
    if args.write_deduped and (len(specs) != 1 or not specs[0].is_file):
        raise ValueError("--write-deduped needs exactly one --input file")
    for src in specs:
        src.check()
    fields = parse_fields(args.field)

    try:
        sources = [
            SourceRecords(src.name, src.load(fields=fields, id_field=args.id_field))
            for src in specs
        ]
    except (RecordError, UnicodeDecodeError) as e:
        subject = [src.descriptor() for src in specs]
        return _error_report(args, kind=DEDUP_KIND, subject=subject, inputs=[], error=str(e))
    subject = [src.descriptor() for src in specs]

    result = dedup_records(
        sources, near_duplicates=args.near_dup, threshold=args.near_dup_threshold
    )

    failed = []
    if "exact-duplicates" in fail_on and result.exact_groups:
        failed.append("exact-duplicates")
    if "near-duplicates" in fail_on and result.near_groups:
        failed.append("near-duplicates")

    summary: dict[str, Any] = {
        "record_count": result.record_count,
        "exact_duplicate_group_count": len(result.exact_groups),
        "exact_duplicate_count": result.exact_duplicate_count,
        "removable_count": len(result.removable),
        "kept_count": result.record_count - len(result.removable),
        "empty_record_count": result.empty_count,
        "fail_on": fail_on,
        "failed_checks": failed,
    }
    details: dict[str, Any] = {
        "parameters": {
            "fields": list(fields),
            "normalization": "NFKC, lowercase, \\w+ tokens",
            "near_duplicates": bool(args.near_dup),
        },
        "exact_groups": result.exact_groups,
        "removable": result.removable,
    }
    if result.near_groups is not None:
        summary["near_duplicate_group_count"] = len(result.near_groups)
        details["parameters"]["near_dup_threshold"] = args.near_dup_threshold
        details["near_groups"] = result.near_groups
        details["near_pairs"] = result.near_pairs

    if args.write_deduped:
        name, path = specs[0].name, specs[0].path
        if path is None:  # pragma: no cover - rejected above
            raise ValueError("--write-deduped needs a file input")
        out = Path(args.write_deduped).resolve()
        drop = {r["index"] for r in result.removable if r["source"] == name}
        written = write_without(path, drop, out)
        details["deduped_file"] = {"path": str(out), "record_count": written}
        logger.info(f"Wrote {written} records to {out}")

    envelope = build_envelope(
        kind=DEDUP_KIND,
        subject=subject,
        verdict=VERDICT_FAIL if failed else VERDICT_PASS,
        exit_code=EXIT_GATE_FAILED if failed else EXIT_SUCCESS,
        summary=summary,
        details=details,
    )
    return _emit(args, envelope)


def _cmd_verify(args: argparse.Namespace) -> int:
    """Verify the Ed25519 signature of a report file.

    A detached signature (``--signature``, or ``<input>.sig`` when present)
    covers the exact bytes of the report file. Otherwise the legacy embedded
    ``signature`` field of a ``--format legacy-json`` scan is checked.
    """
    scan_path = Path(args.input).resolve()
    key_path = Path(args.public_key).resolve()

    if not scan_path.exists():
        logger.error(f"Scan file not found: {scan_path}")
        return EXIT_CLI_ERROR
    if not key_path.exists():
        logger.error(f"Public key not found: {key_path}")
        return EXIT_CLI_ERROR

    sig_arg = getattr(args, "signature", "") or ""
    sig_path = Path(sig_arg).resolve() if sig_arg else scan_path.with_name(scan_path.name + ".sig")
    if sig_arg and not sig_path.exists():
        logger.error(f"Signature file not found: {sig_path}")
        return EXIT_CLI_ERROR

    try:
        from .signing import canonical_json_bytes, verify_payload

        public_key_pem = key_path.read_text(encoding="utf-8")
        if sig_path.exists():
            payload = scan_path.read_bytes()
            signature_b64 = sig_path.read_text(encoding="ascii").strip()
            base64.b64decode(signature_b64, validate=True)
        else:
            raw = json.loads(scan_path.read_text(encoding="utf-8"))
            signature_b64 = raw.pop("signature", None) if isinstance(raw, dict) else None
            if signature_b64 is None:
                logger.error(f"No signature found: no {sig_path.name} and no embedded signature")
                return EXIT_CLI_ERROR
            payload = canonical_json_bytes(raw)
        valid = verify_payload(
            payload=payload, signature_b64=signature_b64, public_key_pem=public_key_pem
        )
        if valid:
            print("Signature is VALID")
            return EXIT_SUCCESS
        print("Signature is INVALID")
        return EXIT_CLI_ERROR
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return EXIT_CLI_ERROR


def _add_output_args(p: argparse.ArgumentParser, *, legacy: bool) -> None:
    p.add_argument("--out", default="", help="Output file path (default: stdout)")
    choices = [FORMAT_JSON, FORMAT_MARKDOWN] + ([FORMAT_LEGACY] if legacy else [])
    p.add_argument(
        "--format",
        choices=choices,
        default=FORMAT_JSON,
        help=(
            "json (default): report envelope (in-toto Statement v1, canonical JSON); "
            "markdown: human-readable summary"
            + ("; legacy-json: the pre-1.0 bare object (deprecated)" if legacy else "")
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="toolkit-mmqa",
        description=(
            "Dataset pre-flight QA: duplicates, near-duplicates and file-level diffs, "
            "reported as a signable in-toto attestation."
        ),
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )
    p.add_argument(
        "--log-format",
        choices=["text", "json"],
        default="text",
        help="Log format: 'text' (default) or 'json' for structured JSON logging",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # scan subcommand
    s = sub.add_parser("scan", help="Scan a dataset directory and produce a dedupe report.")
    s.add_argument("--root", required=True, help="Root directory to scan")
    _add_output_args(s, legacy=True)
    s.add_argument(
        "--extensions",
        default="",
        help="Comma-separated file extensions to scan (default: all)",
    )
    s.add_argument(
        "--max-file-size",
        type=int,
        default=None,
        help="Maximum file size in bytes to process (files larger are skipped)",
    )
    s.add_argument(
        "--follow-symlinks",
        action="store_true",
        default=False,
        dest="follow_symlinks",
        help="Follow symbolic links (default: skip)",
    )
    s.add_argument(
        "--skip-symlinks",
        action="store_false",
        dest="follow_symlinks",
        help="Skip symbolic links instead of following them",
    )
    s.add_argument(
        "--progress",
        action="store_true",
        default=False,
        help="Show progress bar during scan",
    )
    s.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Threads hashing files in parallel (default: 1)",
    )
    s.add_argument(
        "--fail-on",
        default="",
        help=(
            "Comma-separated checks that fail the scan (verdict 'fail', exit 1): "
            + ", ".join(SCAN_CHECKS)
        ),
    )
    s.add_argument(
        "--sign",
        action="store_true",
        default=False,
        help=(
            "Sign the report with an Ed25519 private key. With the default JSON "
            "format a detached signature is written to <out>.sig"
        ),
    )
    s.add_argument(
        "--sign-key",
        default="",
        help="Path to Ed25519 private key PEM file (required with --sign)",
    )
    s.add_argument(
        "--near-dup-text",
        action="store_true",
        default=False,
        help=(
            "Also find near-duplicate text files with MinHash (character trigrams). "
            "Files that are not UTF-8 text are skipped. All text files are loaded "
            "into memory; limit input with --extensions / --max-file-size."
        ),
    )
    s.add_argument(
        "--near-dup-threshold",
        type=float,
        default=None,
        help=(
            "Estimated Jaccard similarity (0-1) at or above which two text files "
            f"are near-duplicates (default: {DEFAULT_NEAR_DUP_THRESHOLD}). "
            "Requires --near-dup-text."
        ),
    )
    s.add_argument(
        "--image-checks",
        action="store_true",
        default=False,
        help=(
            "Decode every image (by extension), report corrupt files, resolution "
            "statistics and perceptual-hash near-duplicates. Needs the [image] extra"
        ),
    )
    s.add_argument(
        "--audio-checks",
        action="store_true",
        default=False,
        help=(
            "Decode every audio file (by extension) to find corrupt, truncated or "
            "empty files and report durations. WAV works out of the box; FLAC, Ogg, "
            "MP3 and AIFF need the [audio] extra"
        ),
    )
    s.add_argument(
        "--image-hash-distance",
        type=int,
        default=DEFAULT_MAX_DISTANCE,
        help=(
            "Maximum pHash Hamming distance (of 64 bits) for two images to be "
            f"near-duplicates (default: {DEFAULT_MAX_DISTANCE})"
        ),
    )
    s.set_defaults(func=_cmd_scan)

    # report subcommand
    r = sub.add_parser("report", help="Generate summary statistics from a scan result file.")
    r.add_argument("--input", required=True, help="Path to scan result JSON file")
    _add_output_args(r, legacy=True)
    r.set_defaults(func=_cmd_report)

    # diff subcommand
    d = sub.add_parser("diff", help="Compare two scan result files and show changes.")
    d.add_argument("--old", required=True, help="Path to old scan result JSON file")
    d.add_argument("--new", required=True, help="Path to new scan result JSON file")
    _add_output_args(d, legacy=True)
    d.set_defaults(func=_cmd_diff)

    # contamination subcommand
    c = sub.add_parser(
        "contamination",
        help="Find evaluation or benchmark records that also appear in training data.",
        description=(
            "Check evaluation splits and benchmarks against training data with exact, "
            "word n-gram and (optionally) MinHash matching. Exit 1 when a target's "
            "contaminated fraction exceeds --max-contamination."
        ),
    )
    c.add_argument(
        "--train",
        action="append",
        required=True,
        metavar="[NAME=]PATH",
        help="Training data file (JSONL, JSON, CSV or text). Repeat for several files",
    )
    c.add_argument(
        "--eval",
        action="append",
        metavar="[NAME=]PATH",
        help="Evaluation split to check. Repeatable",
    )
    c.add_argument(
        "--benchmark",
        action="append",
        metavar="[NAME=]PATH",
        help="Benchmark file to check (same as --eval, reported with role 'benchmark')",
    )
    c.add_argument(
        "--field",
        default="text",
        help="Comma-separated record field(s) holding the text (default: text)",
    )
    c.add_argument("--train-field", default="", help="Field(s) for training files")
    c.add_argument("--eval-field", default="", help="Field(s) for evaluation/benchmark files")
    c.add_argument("--id-field", default=None, help="Record field reported as the record id")
    c.add_argument(
        "--methods",
        default="exact,ngram",
        help="Comma-separated: exact, ngram, minhash (default: exact,ngram)",
    )
    c.add_argument(
        "--ngram-size",
        type=int,
        default=DEFAULT_NGRAM_SIZE,
        help=f"Word n-gram length (default: {DEFAULT_NGRAM_SIZE})",
    )
    c.add_argument(
        "--min-ngram-size",
        type=int,
        default=DEFAULT_MIN_NGRAM_SIZE,
        help=(
            "Records shorter than --ngram-size but at least this many tokens are "
            f"matched as a whole (default: {DEFAULT_MIN_NGRAM_SIZE})"
        ),
    )
    c.add_argument(
        "--ngram-threshold",
        type=float,
        default=0.0,
        help="Minimum fraction of a record's n-grams found in training data (0 = any)",
    )
    c.add_argument(
        "--minhash-threshold",
        type=float,
        default=DEFAULT_MINHASH_THRESHOLD,
        help=f"Minimum estimated Jaccard similarity (default: {DEFAULT_MINHASH_THRESHOLD})",
    )
    c.add_argument(
        "--max-contamination",
        type=float,
        default=0.0,
        help="Fail when a target's contaminated fraction exceeds this (default: 0)",
    )
    c.add_argument(
        "--max-train-matches",
        type=int,
        default=5,
        help="Training records listed per contaminated record (default: 5)",
    )
    _add_output_args(c, legacy=False)
    c.set_defaults(func=_cmd_contamination)

    # dedup subcommand
    dd = sub.add_parser(
        "dedup",
        help="Find duplicate and near-duplicate records in JSONL/JSON/CSV/text datasets.",
    )
    dd.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="[NAME=]PATH",
        help="Dataset file. Repeat to deduplicate across several files",
    )
    dd.add_argument(
        "--field",
        default="text",
        help="Comma-separated record field(s) holding the text (default: text)",
    )
    dd.add_argument("--id-field", default=None, help="Record field reported as the record id")
    dd.add_argument(
        "--near-dup",
        action="store_true",
        default=False,
        help="Also find near-duplicate records (MinHash on character trigrams)",
    )
    dd.add_argument(
        "--near-dup-threshold",
        type=float,
        default=DEFAULT_NEAR_DUP_THRESHOLD,
        help=f"Estimated Jaccard similarity for --near-dup (default: {DEFAULT_NEAR_DUP_THRESHOLD})",
    )
    dd.add_argument(
        "--fail-on",
        default="",
        help="Comma-separated checks that fail the run (exit 1): " + ", ".join(RECORD_CHECKS),
    )
    dd.add_argument(
        "--write-deduped",
        default="",
        metavar="PATH",
        help=(
            "Write a copy of the (single, JSONL or text) input without removable records; "
            "the first record of each group is kept"
        ),
    )
    _add_output_args(dd, legacy=False)
    dd.set_defaults(func=_cmd_dedup)

    # verify subcommand
    v = sub.add_parser("verify", help="Verify the Ed25519 signature of a report file.")
    v.add_argument("--input", required=True, help="Path to the signed report JSON file")
    v.add_argument("--public-key", required=True, help="Path to Ed25519 public key PEM file")
    v.add_argument(
        "--signature",
        default="",
        help="Detached signature file (default: <input>.sig if it exists)",
    )
    v.set_defaults(func=_cmd_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code: 0 pass, 1 a ``--fail-on`` check failed, 2 usage or input
        error, 3 unexpected error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging format
    if args.log_format == "json":
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        logging.root.handlers = []
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.DEBUG if args.verbose else logging.WARNING)
    else:
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.WARNING,
            format="%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stderr,
        )

    # Validate --sign requires --sign-key
    if getattr(args, "sign", False) and not getattr(args, "sign_key", ""):
        logger.error("--sign requires --sign-key <path-to-private-key>")
        return EXIT_CLI_ERROR

    try:
        return int(args.func(args))
    except (ValueError, KeyError, FileNotFoundError, PermissionError, OSError) as e:
        logger.error(f"{type(e).__name__}: {e}")
        return EXIT_CLI_ERROR
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return EXIT_UNEXPECTED_ERROR
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(
            "\nAn unexpected error occurred. Please report this issue.",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED_ERROR
