"""Test helpers shared across test modules."""

from __future__ import annotations

from typing import Any


def payload(report: dict[str, Any]) -> dict[str, Any]:
    """Return the tool-specific payload of a CLI report.

    Report envelopes carry the scan and diff objects in ``predicate.details``
    and the report statistics in ``predicate.summary``. Legacy objects are
    returned unchanged.
    """
    if report.get("_type") != "https://in-toto.io/Statement/v1":
        return report
    predicate = report["predicate"]
    if predicate["kind"] == "mmqa.report":
        return predicate["summary"]
    return predicate["details"]
