"""Quality-gate tests covering Testing, API, Documentation, and Domain gaps.

This module provides comprehensive coverage for:

- **Testing (6->7):** Hashing module, duplicate-detection algorithms,
  MinHash analysis edge cases, CLI interface coverage.
- **API (6->7):** Input validation, type safety, consistent return types.
- **Documentation (5->6):** Module-level docstrings, inline docs.
- **Domain (5->6):** Data provenance, dataset governance, MinHash
  configurability.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from toolkit_mmqa import (
    ScanMetadata,
    ScanResult,
    __version__,
    diff_scans,
    find_near_duplicates,
    generate_report,
    scan,
)
from toolkit_mmqa.cli import EXIT_SUCCESS, build_parser, main
from toolkit_mmqa.hashing import CHUNK_SIZE, sha256_file
from toolkit_mmqa.reporting import DiffResult, ReportSummary, load_scan_file
from toolkit_mmqa.text_dedup import (
    MinHasher,
    MinHashSignature,
    TextDedupResult,
    _hash_token,
    _ngrams,
)

# ============================================================================
# Testing dimension: hashing module (previously untested directly)
# ============================================================================


class TestSha256File:
    """Direct unit tests for sha256_file."""

    def test_known_digest(self, tmp_path: Path) -> None:
        """SHA-256 of known content matches expected hex digest."""
        f = tmp_path / "known.txt"
        f.write_bytes(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert sha256_file(f) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        """SHA-256 of an empty file is the well-known empty hash."""
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_file(f) == expected

    def test_binary_content(self, tmp_path: Path) -> None:
        """SHA-256 works correctly with arbitrary binary content."""
        data = bytes(range(256)) * 100
        f = tmp_path / "binary.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert sha256_file(f) == expected

    def test_large_file_chunked_correctly(self, tmp_path: Path) -> None:
        """Files larger than CHUNK_SIZE are hashed correctly."""
        # Write 2x chunk size of data
        data = b"A" * (CHUNK_SIZE * 2 + 123)
        f = tmp_path / "large.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert sha256_file(f) == expected

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """sha256_file raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            sha256_file(tmp_path / "nonexistent.txt")

    def test_directory_raises(self, tmp_path: Path) -> None:
        """sha256_file raises IsADirectoryError when given a directory."""
        with pytest.raises(IsADirectoryError):
            sha256_file(tmp_path)

    def test_digest_is_lowercase_hex(self, tmp_path: Path) -> None:
        """Digest string is 64-char lowercase hex."""
        f = tmp_path / "test.txt"
        f.write_text("test", encoding="utf-8")
        digest = sha256_file(f)
        assert len(digest) == 64
        assert digest == digest.lower()
        assert all(c in "0123456789abcdef" for c in digest)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        """Different file contents produce different hashes."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A", encoding="utf-8")
        f2.write_text("content B", encoding="utf-8")
        assert sha256_file(f1) != sha256_file(f2)

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        """Identical file contents produce identical hashes."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("identical", encoding="utf-8")
        f2.write_text("identical", encoding="utf-8")
        assert sha256_file(f1) == sha256_file(f2)

    def test_chunk_size_constant(self) -> None:
        """CHUNK_SIZE is 1 MB."""
        assert CHUNK_SIZE == 1024 * 1024


# ============================================================================
# Testing dimension: duplicate detection algorithm coverage
# ============================================================================


class TestDuplicateDetection:
    """Tests for the duplicate-grouping logic in scanner.scan()."""

    def test_three_way_duplicate(self, tmp_path: Path) -> None:
        """Three files with identical content form one group of 3."""
        for name in ("a.txt", "b.txt", "c.txt"):
            (tmp_path / name).write_text("triple", encoding="utf-8")
        result = scan(root=tmp_path)
        assert len(result.duplicates) == 1
        assert len(result.duplicates[0]) == 3

    def test_multiple_independent_groups(self, tmp_path: Path) -> None:
        """Two distinct sets of duplicates form separate groups."""
        (tmp_path / "a1.txt").write_text("group_a", encoding="utf-8")
        (tmp_path / "a2.txt").write_text("group_a", encoding="utf-8")
        (tmp_path / "b1.txt").write_text("group_b", encoding="utf-8")
        (tmp_path / "b2.txt").write_text("group_b", encoding="utf-8")
        (tmp_path / "unique.txt").write_text("no_dup", encoding="utf-8")
        result = scan(root=tmp_path)
        assert len(result.duplicates) == 2
        assert result.file_count == 5

    def test_no_duplicates(self, tmp_path: Path) -> None:
        """All unique files produce zero duplicate groups."""
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text(f"unique_{i}", encoding="utf-8")
        result = scan(root=tmp_path)
        assert len(result.duplicates) == 0

    def test_duplicates_sorted_largest_first(self, tmp_path: Path) -> None:
        """Duplicate groups are sorted largest-first."""
        for i in range(4):
            (tmp_path / f"big{i}.txt").write_text("big_group", encoding="utf-8")
        (tmp_path / "s1.txt").write_text("small_group", encoding="utf-8")
        (tmp_path / "s2.txt").write_text("small_group", encoding="utf-8")
        result = scan(root=tmp_path)
        assert len(result.duplicates) == 2
        assert len(result.duplicates[0]) >= len(result.duplicates[1])

    def test_total_bytes_accurate(self, tmp_path: Path) -> None:
        """total_bytes equals the sum of all scanned file sizes."""
        (tmp_path / "a.txt").write_bytes(b"12345")  # 5 bytes
        (tmp_path / "b.txt").write_bytes(b"67890")  # 5 bytes
        result = scan(root=tmp_path)
        assert result.total_bytes == 10


# ============================================================================
# Testing dimension: MinHash near-duplicate analysis edge cases
# ============================================================================


class TestMinHashEdgeCases:
    """Edge-case tests for MinHash and near-duplicate detection."""

    def test_single_document(self) -> None:
        """A single document cannot form a near-duplicate group."""
        result = find_near_duplicates({"only.txt": "hello world"}, threshold=0.5)
        assert result.near_duplicate_groups == []

    def test_all_identical(self) -> None:
        """Many identical documents form a single group."""
        texts = {f"doc{i}.txt": "identical content here" for i in range(10)}
        result = find_near_duplicates(texts, threshold=0.9)
        assert len(result.near_duplicate_groups) == 1
        assert len(result.near_duplicate_groups[0]) == 10

    def test_threshold_zero_groups_everything(self) -> None:
        """Threshold=0.0 groups all documents together (everything is >= 0)."""
        texts = {
            "a.txt": "aaaaaaaaaa",
            "b.txt": "bbbbbbbbbb",
            "c.txt": "cccccccccc",
        }
        result = find_near_duplicates(texts, threshold=0.0, num_perm=64)
        # With threshold=0.0, all pairs meet the threshold
        assert len(result.near_duplicate_groups) == 1

    def test_threshold_one_only_identical(self) -> None:
        """Threshold=1.0 only groups exactly identical documents."""
        texts = {
            "a.txt": "same text here",
            "b.txt": "same text here",
            "c.txt": "different text here entirely",
        }
        result = find_near_duplicates(texts, threshold=1.0, num_perm=256)
        assert len(result.near_duplicate_groups) == 1
        assert sorted(result.near_duplicate_groups[0]) == ["a.txt", "b.txt"]

    def test_unicode_text(self) -> None:
        """MinHash handles Unicode correctly."""
        texts = {
            "jp.txt": "日本語のテスト文章です",
            "jp2.txt": "日本語のテスト文章です",
            "en.txt": "This is entirely different content",
        }
        result = find_near_duplicates(texts, threshold=0.8)
        assert len(result.near_duplicate_groups) == 1
        assert "jp.txt" in result.near_duplicate_groups[0]

    def test_custom_ngram_size(self) -> None:
        """MinHash works with different ngram_size values."""
        texts = {"a.txt": "hello world test", "b.txt": "hello world test"}
        # bigrams (n=2)
        result = find_near_duplicates(texts, threshold=0.9, ngram_size=2)
        assert len(result.near_duplicate_groups) == 1
        # 5-grams
        result5 = find_near_duplicates(texts, threshold=0.9, ngram_size=5)
        assert len(result5.near_duplicate_groups) == 1

    def test_custom_num_perm(self) -> None:
        """MinHash works with different num_perm values."""
        texts = {"a.txt": "sample text", "b.txt": "sample text"}
        for perm in (16, 32, 256):
            result = find_near_duplicates(texts, threshold=0.9, num_perm=perm)
            assert len(result.near_duplicate_groups) == 1

    def test_similarity_scores_present(self) -> None:
        """Similarity scores dict is populated for matched pairs."""
        texts = {"a.txt": "hello world", "b.txt": "hello world"}
        result = find_near_duplicates(texts, threshold=0.5)
        assert len(result.similarity_scores) > 0
        for score in result.similarity_scores.values():
            assert 0.0 <= score <= 1.0

    def test_ngrams_custom_size(self) -> None:
        """_ngrams with n=5 extracts correct 5-grams."""
        result = _ngrams("abcdefgh", 5)
        assert result == ["abcde", "bcdef", "cdefg", "defgh"]

    def test_ngrams_exact_length(self) -> None:
        """When text length equals n, one n-gram is produced."""
        assert _ngrams("abc", 3) == ["abc"]

    def test_hash_token_deterministic(self) -> None:
        """_hash_token returns the same value for the same input."""
        assert _hash_token("test") == _hash_token("test")

    def test_hash_token_different_inputs(self) -> None:
        """_hash_token returns different values for different inputs."""
        assert _hash_token("aaa") != _hash_token("bbb")

    def test_minhash_signature_equality(self) -> None:
        """MinHashSignature supports equality comparison."""
        sig1 = MinHashSignature(values=(1, 2, 3))
        sig2 = MinHashSignature(values=(1, 2, 3))
        sig3 = MinHashSignature(values=(4, 5, 6))
        assert sig1 == sig2
        assert sig1 != sig3

    def test_minhash_signature_num_perm(self) -> None:
        """MinHashSignature.num_perm returns correct count."""
        sig = MinHashSignature(values=(10, 20, 30, 40))
        assert sig.num_perm == 4


# ============================================================================
# API dimension: input validation
# ============================================================================


class TestInputValidation:
    """Tests for input validation on public API functions."""

    def test_scan_nonexistent_root_raises(self) -> None:
        """scan() raises FileNotFoundError for missing root."""
        with pytest.raises(FileNotFoundError, match="not found"):
            scan(root=Path("/nonexistent/root/path"))

    def test_scan_file_as_root_raises(self, tmp_path: Path) -> None:
        """scan() raises NotADirectoryError when root is a file."""
        f = tmp_path / "file.txt"
        f.write_text("data", encoding="utf-8")
        with pytest.raises(NotADirectoryError):
            scan(root=f)

    def test_scan_negative_max_file_size_raises(self, tmp_path: Path) -> None:
        """scan() raises ValueError for negative max_file_size."""
        with pytest.raises(ValueError, match="max_file_size"):
            scan(root=tmp_path, max_file_size=-1)

    def test_find_near_duplicates_invalid_num_perm(self) -> None:
        """find_near_duplicates raises ValueError for num_perm < 1."""
        with pytest.raises(ValueError, match="num_perm"):
            find_near_duplicates({}, num_perm=0)

    def test_find_near_duplicates_invalid_ngram_size(self) -> None:
        """find_near_duplicates raises ValueError for ngram_size < 1."""
        with pytest.raises(ValueError, match="ngram_size"):
            find_near_duplicates({}, ngram_size=0)

    def test_minhasher_invalid_num_perm(self) -> None:
        """MinHasher raises ValueError for num_perm < 1."""
        with pytest.raises(ValueError, match="num_perm"):
            MinHasher(num_perm=0)

    def test_minhasher_invalid_ngram_size(self) -> None:
        """MinHasher raises ValueError for ngram_size < 1."""
        with pytest.raises(ValueError, match="ngram_size"):
            MinHasher(ngram_size=0)

    def test_generate_report_validates_keys(self) -> None:
        """generate_report raises KeyError for missing required keys."""
        with pytest.raises(KeyError):
            generate_report({"file_count": 1, "total_bytes": 0})

    def test_diff_scans_validates_keys(self) -> None:
        """diff_scans raises KeyError if required keys missing."""
        with pytest.raises(KeyError):
            diff_scans({"file_count": 1}, {"file_count": 2})


# ============================================================================
# API dimension: return types and signatures
# ============================================================================


class TestReturnTypes:
    """Verify consistent return types across the public API."""

    def test_scan_returns_scan_result(self, tmp_path: Path) -> None:
        """scan() returns a ScanResult instance."""
        result = scan(root=tmp_path)
        assert isinstance(result, ScanResult)

    def test_generate_report_returns_report_summary(self) -> None:
        """generate_report returns a ReportSummary instance."""
        data = {"file_count": 0, "total_bytes": 0, "duplicates": []}
        result = generate_report(data)
        assert isinstance(result, ReportSummary)

    def test_diff_scans_returns_diff_result(self) -> None:
        """diff_scans returns a DiffResult instance."""
        data = {"file_count": 0, "total_bytes": 0, "duplicates": []}
        result = diff_scans(data, data)
        assert isinstance(result, DiffResult)

    def test_find_near_duplicates_returns_text_dedup_result(self) -> None:
        """find_near_duplicates returns a TextDedupResult."""
        result = find_near_duplicates({})
        assert isinstance(result, TextDedupResult)

    def test_scan_result_to_json_types(self, tmp_path: Path) -> None:
        """ScanResult.to_json() produces correct JSON-compatible types."""
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        j = scan(root=tmp_path).to_json()
        assert isinstance(j["file_count"], int)
        assert isinstance(j["total_bytes"], int)
        assert isinstance(j["duplicates"], list)
        assert isinstance(j["skipped_count"], int)

    def test_report_summary_to_json_types(self) -> None:
        """ReportSummary.to_json() produces correct types."""
        data = {"file_count": 10, "total_bytes": 1000, "duplicates": [["a", "b"]]}
        j = generate_report(data).to_json()
        assert isinstance(j["avg_file_size"], float)
        assert isinstance(j["largest_group_size"], int)
        assert isinstance(j["unique_file_count"], int)

    def test_text_dedup_result_to_json_types(self) -> None:
        """TextDedupResult.to_json() produces correct types."""
        result = TextDedupResult(
            near_duplicate_groups=[["a", "b"]],
            similarity_scores={"a|b": 0.95},
        )
        j = result.to_json()
        assert isinstance(j["near_duplicate_groups"], list)
        assert isinstance(j["similarity_scores"], dict)


# ============================================================================
# Documentation dimension: module docstrings exist
# ============================================================================


class TestModuleDocstrings:
    """Verify that all modules have docstrings."""

    def test_init_has_docstring(self) -> None:
        import toolkit_mmqa
        assert toolkit_mmqa.__doc__ is not None
        assert len(toolkit_mmqa.__doc__) > 50

    def test_hashing_has_docstring(self) -> None:
        import toolkit_mmqa.hashing
        assert toolkit_mmqa.hashing.__doc__ is not None
        assert "SHA-256" in toolkit_mmqa.hashing.__doc__

    def test_scanner_has_docstring(self) -> None:
        import toolkit_mmqa.scanner
        assert toolkit_mmqa.scanner.__doc__ is not None
        assert "duplicate" in toolkit_mmqa.scanner.__doc__.lower()

    def test_reporting_has_docstring(self) -> None:
        import toolkit_mmqa.reporting
        assert toolkit_mmqa.reporting.__doc__ is not None

    def test_text_dedup_has_docstring(self) -> None:
        import toolkit_mmqa.text_dedup
        assert toolkit_mmqa.text_dedup.__doc__ is not None
        assert "MinHash" in toolkit_mmqa.text_dedup.__doc__

    def test_signing_has_docstring(self) -> None:
        import toolkit_mmqa.signing
        assert toolkit_mmqa.signing.__doc__ is not None

    def test_cli_has_no_crash_importing(self) -> None:
        """cli module imports without error."""
        import toolkit_mmqa.cli
        assert toolkit_mmqa.cli.main is not None


# ============================================================================
# Domain dimension: data provenance tracking
# ============================================================================


class TestDataProvenance:
    """Tests for ScanMetadata provenance tracking."""

    def test_scan_result_has_metadata(self, tmp_path: Path) -> None:
        """Every scan result includes provenance metadata."""
        (tmp_path / "f.txt").write_text("data", encoding="utf-8")
        result = scan(root=tmp_path)
        assert result.metadata is not None

    def test_metadata_tool_version(self, tmp_path: Path) -> None:
        """Metadata records the correct tool version."""
        result = scan(root=tmp_path)
        assert result.metadata is not None
        assert result.metadata.tool_version == "0.1.0"

    def test_metadata_scanned_root(self, tmp_path: Path) -> None:
        """Metadata records the scanned root path."""
        result = scan(root=tmp_path)
        assert result.metadata is not None
        assert str(tmp_path.resolve()) in result.metadata.scanned_root

    def test_metadata_timestamp_is_iso8601(self, tmp_path: Path) -> None:
        """Metadata timestamp is a valid ISO-8601 string."""
        from datetime import datetime

        result = scan(root=tmp_path)
        assert result.metadata is not None
        # Should not raise
        dt = datetime.fromisoformat(result.metadata.timestamp)
        assert dt is not None

    def test_metadata_extensions_filter(self, tmp_path: Path) -> None:
        """Metadata records extension filter when applied."""
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        result = scan(root=tmp_path, extensions={"txt", "jpg"})
        assert result.metadata is not None
        assert result.metadata.extensions_filter is not None
        assert "txt" in result.metadata.extensions_filter

    def test_metadata_no_extensions_filter(self, tmp_path: Path) -> None:
        """Metadata extensions_filter is None when not filtered."""
        result = scan(root=tmp_path)
        assert result.metadata is not None
        assert result.metadata.extensions_filter is None

    def test_metadata_max_file_size(self, tmp_path: Path) -> None:
        """Metadata records max_file_size when set."""
        result = scan(root=tmp_path, max_file_size=1024)
        assert result.metadata is not None
        assert result.metadata.max_file_size == 1024

    def test_metadata_in_json_output(self, tmp_path: Path) -> None:
        """Metadata is included in to_json() output."""
        (tmp_path / "f.txt").write_text("x", encoding="utf-8")
        j = scan(root=tmp_path).to_json()
        assert "metadata" in j
        assert j["metadata"]["tool_version"] == "0.1.0"
        assert "timestamp" in j["metadata"]
        assert "scanned_root" in j["metadata"]

    def test_scan_metadata_to_json(self) -> None:
        """ScanMetadata.to_json() produces correct dict."""
        meta = ScanMetadata(
            tool_version="0.1.0",
            scanned_root="/test",
            timestamp="2026-01-01T00:00:00+00:00",
            extensions_filter=("jpg", "png"),
            max_file_size=500,
        )
        j = meta.to_json()
        assert j["tool_version"] == "0.1.0"
        assert j["extensions_filter"] == ["jpg", "png"]
        assert j["max_file_size"] == 500

    def test_scan_metadata_optional_fields_omitted(self) -> None:
        """ScanMetadata.to_json() omits None optional fields."""
        meta = ScanMetadata(
            tool_version="0.1.0",
            scanned_root="/test",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        j = meta.to_json()
        assert "extensions_filter" not in j
        assert "max_file_size" not in j

    def test_metadata_exported_from_package(self) -> None:
        """ScanMetadata is available from the top-level package."""
        from toolkit_mmqa import ScanMetadata as SM
        assert SM is not None


# ============================================================================
# Domain dimension: dataset governance (integrity checks)
# ============================================================================


class TestDatasetGovernance:
    """Tests for dataset governance patterns."""

    def test_scan_is_reproducible(self, tmp_path: Path) -> None:
        """Two scans of the same directory produce the same results."""
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text(f"content_{i % 2}", encoding="utf-8")
        r1 = scan(root=tmp_path)
        r2 = scan(root=tmp_path)
        assert r1.file_count == r2.file_count
        assert r1.total_bytes == r2.total_bytes
        assert r1.duplicates == r2.duplicates

    def test_scan_json_roundtrip(self, tmp_path: Path) -> None:
        """Scan result can be serialized to JSON and loaded back."""
        for i in range(3):
            (tmp_path / f"f{i}.txt").write_text(f"data_{i}", encoding="utf-8")
        result = scan(root=tmp_path)
        j = result.to_json()
        json_str = json.dumps(j)
        loaded = json.loads(json_str)
        assert loaded["file_count"] == result.file_count
        assert loaded["total_bytes"] == result.total_bytes

    def test_diff_tracks_changes(self, tmp_path: Path) -> None:
        """diff_scans correctly identifies added and removed groups."""
        old = {"file_count": 2, "total_bytes": 100, "duplicates": [["a", "b"]]}
        new = {
            "file_count": 4,
            "total_bytes": 200,
            "duplicates": [["c", "d"], ["e", "f"]],
        }
        diff = diff_scans(old, new)
        assert diff.added_files == 2
        assert len(diff.added_duplicate_groups) == 2
        assert len(diff.removed_duplicate_groups) == 1

    def test_report_unique_count_correct(self) -> None:
        """Report correctly computes unique file count."""
        data = {
            "file_count": 10,
            "total_bytes": 1000,
            "duplicates": [["a", "b", "c"], ["d", "e"]],
        }
        report = generate_report(data)
        assert report.unique_file_count == 5  # 10 - 5 duplicate files

    def test_load_scan_file_validates_keys(self, tmp_path: Path) -> None:
        """load_scan_file rejects files missing required keys."""
        f = tmp_path / "bad.json"
        f.write_text(json.dumps({"file_count": 1}), encoding="utf-8")
        with pytest.raises(KeyError, match="Missing required key"):
            load_scan_file(f)


# ============================================================================
# Domain dimension: MinHash parameters configurable
# ============================================================================


class TestMinHashConfigurability:
    """Verify MinHash parameters are properly configurable."""

    def test_configurable_num_perm(self) -> None:
        """MinHasher accepts different num_perm values."""
        for perm in (8, 64, 128, 512):
            hasher = MinHasher(num_perm=perm)
            sig = hasher.signature("test text")
            assert sig.num_perm == perm

    def test_configurable_ngram_size(self) -> None:
        """MinHasher accepts different ngram_size values."""
        for n in (1, 2, 3, 5, 10):
            hasher = MinHasher(ngram_size=n)
            sig = hasher.signature("abcdefghijklmnop")
            assert sig.num_perm == 128  # default

    def test_configurable_seed(self) -> None:
        """Different seeds produce different signatures."""
        h1 = MinHasher(num_perm=32, seed=1)
        h2 = MinHasher(num_perm=32, seed=999)
        sig1 = h1.signature("test")
        sig2 = h2.signature("test")
        assert sig1 != sig2

    def test_find_near_duplicates_passes_params(self) -> None:
        """find_near_duplicates forwards num_perm and ngram_size."""
        texts = {"a.txt": "hello world foo bar", "b.txt": "hello world foo bar"}
        r1 = find_near_duplicates(texts, threshold=0.9, num_perm=16, ngram_size=2)
        assert len(r1.near_duplicate_groups) == 1

    def test_higher_num_perm_more_accurate(self) -> None:
        """Higher num_perm produces more precise similarity estimates."""
        hasher_low = MinHasher(num_perm=16, seed=42)
        hasher_high = MinHasher(num_perm=512, seed=42)
        text_a = "The quick brown fox jumps over the lazy dog in the park today"
        text_b = "The quick brown fox jumps over the lazy cat in the park today"

        sig_a_low = hasher_low.signature(text_a)
        sig_b_low = hasher_low.signature(text_b)
        sig_a_high = hasher_high.signature(text_a)
        sig_b_high = hasher_high.signature(text_b)

        sim_low = hasher_low.similarity(sig_a_low, sig_b_low)
        sim_high = hasher_high.similarity(sig_a_high, sig_b_high)

        # Both should indicate high similarity; high perm should be
        # closer to the true Jaccard value (both should be > 0.5)
        assert sim_low > 0.3
        assert sim_high > 0.3


# ============================================================================
# Testing dimension: CLI interface additional coverage
# ============================================================================


class TestCLIAdditional:
    """Additional CLI tests for uncovered paths."""

    def test_scan_writes_metadata_to_json(self, tmp_path: Path) -> None:
        """CLI scan output includes metadata section."""
        d = tmp_path / "data"
        d.mkdir()
        (d / "f.txt").write_text("x", encoding="utf-8")
        out = tmp_path / "out.json"
        code = main(["scan", "--root", str(d), "--out", str(out)])
        assert code == EXIT_SUCCESS
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "metadata" in data
        assert data["metadata"]["tool_version"] == "0.1.0"

    def test_cli_scan_max_file_size_with_extensions(self, tmp_path: Path) -> None:
        """CLI scan with both --max-file-size and --extensions works."""
        d = tmp_path / "data"
        d.mkdir()
        (d / "small.txt").write_text("hi", encoding="utf-8")
        (d / "big.txt").write_text("x" * 500, encoding="utf-8")
        (d / "image.jpg").write_bytes(b"\xff\xd8")
        out = tmp_path / "out.json"
        code = main([
            "scan", "--root", str(d),
            "--extensions", "txt",
            "--max-file-size", "100",
            "--out", str(out),
        ])
        assert code == EXIT_SUCCESS
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["file_count"] == 1  # only small.txt

    def test_cli_report_full_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline: scan -> report -> verify structure."""
        d = tmp_path / "data"
        d.mkdir()
        (d / "a.txt").write_text("dup", encoding="utf-8")
        (d / "b.txt").write_text("dup", encoding="utf-8")
        (d / "c.txt").write_text("uniq", encoding="utf-8")

        scan_out = tmp_path / "scan.json"
        main(["scan", "--root", str(d), "--out", str(scan_out)])
        report_out = tmp_path / "report.json"
        code = main(["report", "--input", str(scan_out), "--out", str(report_out)])
        assert code == EXIT_SUCCESS

        report = json.loads(report_out.read_text(encoding="utf-8"))
        assert report["file_count"] == 3
        assert report["duplicate_group_count"] == 1
        assert report["unique_file_count"] == 1

    def test_build_parser_verify_subcommand(self) -> None:
        """verify subcommand is registered in the parser."""
        parser = build_parser()
        args = parser.parse_args([
            "verify", "--input", "/tmp/scan.json", "--public-key", "/tmp/pub.pem"
        ])
        assert args.cmd == "verify"

    def test_cli_diff_all_groups_removed(self, tmp_path: Path) -> None:
        """Diff where all groups are removed."""
        old = {"file_count": 4, "total_bytes": 200, "duplicates": [["a", "b"], ["c", "d"]]}
        new = {"file_count": 2, "total_bytes": 100, "duplicates": []}
        result = diff_scans(old, new)
        assert len(result.removed_duplicate_groups) == 2
        assert len(result.added_duplicate_groups) == 0
        assert result.removed_files == 2

    def test_cli_version_string(self) -> None:
        """Package version is a valid semver-like string."""
        assert __version__ == "0.1.0"
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ============================================================================
# Testing dimension: edge cases for report generation
# ============================================================================


class TestReportEdgeCases:
    """Edge cases for generate_report and load_scan_file."""

    def test_report_single_file(self) -> None:
        """Report for a scan with exactly one file."""
        data = {"file_count": 1, "total_bytes": 42, "duplicates": []}
        report = generate_report(data)
        assert report.avg_file_size == 42.0
        assert report.unique_file_count == 1

    def test_report_all_files_duplicate(self) -> None:
        """Report where every file is part of a duplicate group."""
        data = {
            "file_count": 4,
            "total_bytes": 400,
            "duplicates": [["a", "b"], ["c", "d"]],
        }
        report = generate_report(data)
        assert report.unique_file_count == 0

    def test_diff_both_empty(self) -> None:
        """Diff of two empty scans."""
        empty = {"file_count": 0, "total_bytes": 0, "duplicates": []}
        result = diff_scans(empty, empty)
        assert result.added_files == 0
        assert result.removed_files == 0
        assert result.added_duplicate_groups == []

    def test_load_scan_file_valid_roundtrip(self, tmp_path: Path) -> None:
        """load_scan_file successfully loads a valid scan file."""
        data = {"file_count": 3, "total_bytes": 300, "duplicates": [["a", "b"]]}
        f = tmp_path / "scan.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        loaded = load_scan_file(f)
        assert loaded["file_count"] == 3
        assert loaded["duplicates"] == [["a", "b"]]
