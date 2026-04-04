"""
CLI command -> ToolSpec mapping for toolkit-mmqa.

Maps the 4 CLI subcommands (scan, report, diff, verify) to ToolSpec contracts
with appropriate permission scope and approval policy.

All commands are READ_ONLY + AUTO -- this toolkit reads dataset directories
and produces QA reports; it never modifies external state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ApprovalPolicy, AuthorityBoundary, PermissionScope, ToolSpec


@dataclass
class ToolkitCommandSpec:
    """Maps a CLI subcommand name to its ToolSpec and authority boundary."""

    command: str
    spec: ToolSpec
    boundary: AuthorityBoundary


def _make_spec(
    name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
) -> ToolSpec:
    """Create a ToolSpec for a read-only CLI command."""
    return ToolSpec(
        name=name,
        description=description,
        category="tool",
        version="0.1.0",
        owner="toolkit-mmqa",
        permission_scope=PermissionScope.READ_ONLY,
        input_schema=input_schema,
        output_schema=None,
        sandbox_requirement=None,
        aliases=None,
    )


_READ_ONLY_AUTO = AuthorityBoundary(
    scope=PermissionScope.READ_ONLY,
    approval=ApprovalPolicy.AUTO,
)

# -- Per-command specs ---------------------------------------------------------

TOOLKIT_TOOL_SPECS: dict[str, ToolkitCommandSpec] = {
    "scan": ToolkitCommandSpec(
        command="scan",
        spec=_make_spec(
            name="scan",
            description=(
                "Scan a dataset directory for duplicate files (text/image/audio) "
                "using content hashing. Read-only; emits a scan result file."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "root": {"type": "string", "description": "Root dataset directory"},
                    "out": {"type": "string", "description": "Output scan result file path"},
                    "extensions": {
                        "type": "string",
                        "description": "Comma-separated file extensions to filter",
                    },
                    "format": {"type": "string", "enum": ["json", "text"]},
                    "max_file_size": {"type": "integer"},
                },
                "required": ["root"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "report": ToolkitCommandSpec(
        command="report",
        spec=_make_spec(
            name="report",
            description=(
                "Generate a human-readable QA report from a scan result file. "
                "Read-only."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "scan_file": {"type": "string", "description": "Path to scan result JSON"},
                    "format": {"type": "string", "enum": ["json", "text"]},
                },
                "required": ["scan_file"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "diff": ToolkitCommandSpec(
        command="diff",
        spec=_make_spec(
            name="diff",
            description=(
                "Compare two scan result files and report additions, removals, "
                "and changed files. Read-only."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "baseline": {"type": "string", "description": "Baseline scan result path"},
                    "candidate": {"type": "string", "description": "Candidate scan result path"},
                    "format": {"type": "string", "enum": ["json", "text"]},
                },
                "required": ["baseline", "candidate"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "verify": ToolkitCommandSpec(
        command="verify",
        spec=_make_spec(
            name="verify",
            description=(
                "Re-hash files listed in a scan result and verify integrity. "
                "Read-only; reports mismatches to stdout."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "scan_file": {"type": "string", "description": "Path to scan result JSON"},
                    "format": {"type": "string", "enum": ["json", "text"]},
                },
                "required": ["scan_file"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
}


def get_tool_spec(command: str) -> ToolkitCommandSpec | None:
    """Return the ToolkitCommandSpec for a CLI subcommand, or None if unknown."""
    return TOOLKIT_TOOL_SPECS.get(command)


__all__ = ["TOOLKIT_TOOL_SPECS", "ToolkitCommandSpec", "get_tool_spec"]
