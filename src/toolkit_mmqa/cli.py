from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .reporting import diff_scans, generate_report, load_scan_file
from .scanner import scan

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_CLI_ERROR = 2
EXIT_UNEXPECTED_ERROR = 3


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


def _cmd_scan(args: argparse.Namespace) -> int:
    """Scan directory for duplicate files."""
    root_path = validate_directory_path(Path(args.root))
    logger.info(f"Scanning directory: {root_path}")

    exts = None
    if args.extensions:
        exts = {
            x.strip().lower().lstrip(".")
            for x in str(args.extensions).split(",")
            if x.strip()
        }
        logger.info(f"Filtering extensions: {', '.join(sorted(exts))}")

    result = scan(root=root_path, extensions=exts)
    logger.info(
        f"Scan complete: {result.file_count} files, "
        f"{len(result.duplicates)} duplicate groups, "
        f"{result.total_bytes:,} bytes"
    )

    out = json.dumps(result.to_json(), indent=2, sort_keys=True)

    if args.out:
        out_path = Path(args.out).resolve()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(out, encoding="utf-8")
            logger.info(f"Report saved to: {out_path}")
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to write output file: {e}")
            return EXIT_CLI_ERROR
    else:
        print(out)

    return EXIT_SUCCESS


def _cmd_report(args: argparse.Namespace) -> int:
    """Generate summary report from a scan result file."""
    scan_path = Path(args.input).resolve()
    if not scan_path.exists():
        logger.error(f"Scan file not found: {scan_path}")
        return EXIT_CLI_ERROR

    try:
        data = load_scan_file(scan_path)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Invalid scan file: {e}")
        return EXIT_CLI_ERROR

    summary = generate_report(data)
    out = json.dumps(summary.to_json(), indent=2, sort_keys=True)

    if args.out:
        out_path = Path(args.out).resolve()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(out, encoding="utf-8")
            logger.info(f"Report saved to: {out_path}")
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to write output file: {e}")
            return EXIT_CLI_ERROR
    else:
        print(out)

    return EXIT_SUCCESS


def _cmd_diff(args: argparse.Namespace) -> int:
    """Compare two scan result files."""
    old_path = Path(args.old).resolve()
    new_path = Path(args.new).resolve()

    for label, p in [("Old", old_path), ("New", new_path)]:
        if not p.exists():
            logger.error(f"{label} scan file not found: {p}")
            return EXIT_CLI_ERROR

    try:
        old_data = load_scan_file(old_path)
        new_data = load_scan_file(new_path)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Invalid scan file: {e}")
        return EXIT_CLI_ERROR

    result = diff_scans(old_data, new_data)
    out = json.dumps(result.to_json(), indent=2, sort_keys=True)

    if args.out:
        out_path = Path(args.out).resolve()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(out, encoding="utf-8")
            logger.info(f"Diff saved to: {out_path}")
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to write output file: {e}")
            return EXIT_CLI_ERROR
    else:
        print(out)

    return EXIT_SUCCESS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="toolkit-mmqa",
        description="Toolkit Multimodal Dataset QA - Detect duplicate files in datasets",
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
    sub = p.add_subparsers(dest="cmd", required=True)

    # scan subcommand
    s = sub.add_parser(
        "scan", help="Scan a dataset directory and produce a dedupe report."
    )
    s.add_argument("--root", required=True, help="Root directory to scan")
    s.add_argument("--out", default="", help="Output file path (default: stdout)")
    s.add_argument(
        "--extensions",
        default="",
        help="Comma-separated file extensions to scan (default: all)",
    )
    s.set_defaults(func=_cmd_scan)

    # report subcommand
    r = sub.add_parser(
        "report", help="Generate summary statistics from a scan result file."
    )
    r.add_argument("--input", required=True, help="Path to scan result JSON file")
    r.add_argument("--out", default="", help="Output file path (default: stdout)")
    r.set_defaults(func=_cmd_report)

    # diff subcommand
    d = sub.add_parser(
        "diff", help="Compare two scan result files and show changes."
    )
    d.add_argument("--old", required=True, help="Path to old scan result JSON file")
    d.add_argument("--new", required=True, help="Path to new scan result JSON file")
    d.add_argument("--out", default="", help="Output file path (default: stdout)")
    d.set_defaults(func=_cmd_diff)

    return p


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 = success, non-zero = error)
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )

    try:
        return int(args.func(args))
    except (ValueError, FileNotFoundError, PermissionError) as e:
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
