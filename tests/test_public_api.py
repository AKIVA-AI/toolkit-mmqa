"""Tests for public API exports from __init__.py — Task 7."""

from __future__ import annotations


def test_public_api_exports() -> None:
    """All expected symbols are exported from toolkit_mmqa."""
    import toolkit_mmqa

    assert hasattr(toolkit_mmqa, "__version__")
    assert hasattr(toolkit_mmqa, "scan")
    assert hasattr(toolkit_mmqa, "ScanResult")
    assert hasattr(toolkit_mmqa, "MinHasher")
    assert hasattr(toolkit_mmqa, "TextDedupResult")
    assert hasattr(toolkit_mmqa, "find_near_duplicates")
    assert hasattr(toolkit_mmqa, "generate_report")
    assert hasattr(toolkit_mmqa, "diff_scans")
    assert hasattr(toolkit_mmqa, "ReportSummary")
    assert hasattr(toolkit_mmqa, "DiffResult")


def test_all_list_complete() -> None:
    """__all__ contains all public names."""
    import toolkit_mmqa

    for name in toolkit_mmqa.__all__:
        assert hasattr(toolkit_mmqa, name), f"Missing export: {name}"


def test_programmatic_scan(tmp_path) -> None:
    """Library can be used programmatically via imports."""
    from toolkit_mmqa import scan, ScanResult

    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    result = scan(root=tmp_path)
    assert isinstance(result, ScanResult)
    assert result.file_count == 1


def test_programmatic_report() -> None:
    """generate_report works via public API."""
    from toolkit_mmqa import generate_report, ReportSummary

    data = {"file_count": 5, "total_bytes": 500, "duplicates": [["a", "b"]]}
    report = generate_report(data)
    assert isinstance(report, ReportSummary)
    assert report.file_count == 5


def test_programmatic_text_dedup() -> None:
    """find_near_duplicates works via public API."""
    from toolkit_mmqa import find_near_duplicates, TextDedupResult

    texts = {"a.txt": "hello world", "b.txt": "hello world"}
    result = find_near_duplicates(texts, threshold=0.8)
    assert isinstance(result, TextDedupResult)
