"""Report envelope v1 (in-toto Statement v1) is the default JSON output."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from toolkit_mmqa import __version__
from toolkit_mmqa.cli import main
from toolkit_mmqa.envelope import (
    PREDICATE_TYPE,
    STATEMENT_TYPE,
    build_envelope,
    canonical_bytes,
    manifest_digest,
)

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "report-envelope.v1.json").read_text(encoding="utf-8"))


def _validate(report: dict) -> None:
    jsonschema.Draft202012Validator(SCHEMA).validate(report)


def _dataset(tmp_path: Path) -> Path:
    root = tmp_path / "ds"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"same")
    (root / "b.txt").write_bytes(b"same")
    (root / "sub" / "c.txt").write_bytes(b"other")
    return root


def _scan(tmp_path: Path, *extra: str) -> tuple[int, Path]:
    out = tmp_path / "scan.json"
    code = main(["scan", "--root", str(_dataset(tmp_path)), "--out", str(out), *extra])
    return code, out


# --- canonical form -----------------------------------------------------------


def test_canonical_bytes_sorted_compact_utf8_newline() -> None:
    assert canonical_bytes({"b": 1, "a": [1, 2], "c": "é"}) == (
        '{"a":[1,2],"b":1,"c":"é"}\n'.encode()
    )


def test_build_envelope_rejects_inconsistent_verdict() -> None:
    subject = [{"name": "x", "digest": {"sha256": "0" * 64}}]
    kw = {"kind": "mmqa.scan", "subject": subject, "summary": {}, "details": {}}
    with pytest.raises(ValueError):
        build_envelope(verdict="pass", exit_code=1, **kw)
    with pytest.raises(ValueError):
        build_envelope(verdict="fail", exit_code=0, **kw)
    with pytest.raises(ValueError):
        build_envelope(verdict="error", exit_code=0, **kw)
    with pytest.raises(ValueError):
        build_envelope(verdict="maybe", exit_code=0, **kw)
    with pytest.raises(ValueError):
        build_envelope(verdict="pass", exit_code=0, **{**kw, "subject": []})


def test_schema_rejects_pass_with_nonzero_exit() -> None:
    env = build_envelope(
        kind="mmqa.scan",
        subject=[{"name": "x", "digest": {"sha256": "0" * 64}}],
        verdict="pass",
        exit_code=0,
        summary={},
        details={},
    )
    _validate(env)
    env["predicate"]["exit_code"] = 1
    with pytest.raises(jsonschema.ValidationError):
        _validate(env)


# --- scan ---------------------------------------------------------------------


def test_scan_default_output_is_canonical_envelope(tmp_path: Path) -> None:
    code, out = _scan(tmp_path)
    assert code == 0
    raw = out.read_bytes()
    report = json.loads(raw)
    _validate(report)
    # The file is exactly its canonical serialization.
    assert raw == canonical_bytes(report)

    assert report["_type"] == STATEMENT_TYPE
    assert report["predicateType"] == PREDICATE_TYPE
    pred = report["predicate"]
    assert pred["tool"] == {"name": "toolkit-mmqa", "version": __version__}
    assert pred["kind"] == "mmqa.scan"
    assert pred["verdict"] == "pass" and pred["exit_code"] == 0
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", pred["created_at"])
    assert pred["summary"]["file_count"] == 3
    assert pred["summary"]["duplicate_group_count"] == 1
    assert pred["summary"]["unique_content_count"] == 2
    assert pred["details"]["duplicates"] == [["a.txt", "b.txt"]]


def test_scan_subject_digest_is_recomputable_from_the_files(tmp_path: Path) -> None:
    """The subject digest is SHA-256 of canonical {path: sha256}, computed independently."""
    _, out = _scan(tmp_path)
    report = json.loads(out.read_bytes())
    expected_map = {
        "a.txt": hashlib.sha256(b"same").hexdigest(),
        "b.txt": hashlib.sha256(b"same").hexdigest(),
        "sub/c.txt": hashlib.sha256(b"other").hexdigest(),
    }
    expected = hashlib.sha256(
        json.dumps(expected_map, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert report["subject"] == [{"name": "ds", "digest": {"sha256": expected}}]
    assert manifest_digest(report["predicate"]["details"]["files"]) == expected


def test_scan_fail_on_exact_duplicates_fails_gate(tmp_path: Path) -> None:
    code, out = _scan(tmp_path, "--fail-on", "exact-duplicates")
    report = json.loads(out.read_bytes())
    _validate(report)
    assert code == 1
    assert report["predicate"]["verdict"] == "fail"
    assert report["predicate"]["exit_code"] == 1
    assert report["predicate"]["summary"]["failed_checks"] == ["exact-duplicates"]


def test_scan_fail_on_passes_when_clean(tmp_path: Path) -> None:
    root = tmp_path / "clean"
    root.mkdir()
    (root / "a.txt").write_bytes(b"one")
    (root / "b.txt").write_bytes(b"two")
    out = tmp_path / "s.json"
    code = main(["scan", "--root", str(root), "--out", str(out), "--fail-on", "exact-duplicates"])
    assert code == 0
    assert json.loads(out.read_bytes())["predicate"]["verdict"] == "pass"


@pytest.mark.parametrize(
    "extra",
    [["--fail-on", "near-duplicates"], ["--fail-on", "bogus"]],
)
def test_scan_fail_on_usage_errors(tmp_path: Path, extra: list[str]) -> None:
    code, out = _scan(tmp_path, *extra)
    assert code == 2
    assert not out.exists()


def test_scan_legacy_json_format(tmp_path: Path) -> None:
    code, out = _scan(tmp_path, "--format", "legacy-json")
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "_type" not in data
    assert data["file_count"] == 3


def test_scan_markdown_format(tmp_path: Path) -> None:
    code, out = _scan(tmp_path, "--format", "markdown")
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "Verdict: **pass**" in text
    assert "| duplicate_group_count | 1 |" in text


def test_scan_sign_requires_out_for_envelope(tmp_path: Path) -> None:
    key = tmp_path / "k.pem"
    key.write_text("unused", encoding="utf-8")
    root = _dataset(tmp_path)
    assert main(["scan", "--root", str(root), "--sign", "--sign-key", str(key)]) == 2


def test_legacy_embedded_signature_still_verifies(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    from toolkit_mmqa.signing import generate_ed25519_keypair

    kp = generate_ed25519_keypair()
    priv, pub = tmp_path / "priv.pem", tmp_path / "pub.pem"
    priv.write_text(kp.private_key_pem, encoding="utf-8")
    pub.write_text(kp.public_key_pem, encoding="utf-8")
    code, out = _scan(tmp_path, "--format", "legacy-json", "--sign", "--sign-key", str(priv))
    assert code == 0
    assert "signature" in json.loads(out.read_text(encoding="utf-8"))
    assert main(["verify", "--input", str(out), "--public-key", str(pub)]) == 0


# --- report and diff ----------------------------------------------------------


def test_report_is_envelope_about_the_scanned_dataset(tmp_path: Path) -> None:
    _, scan_out = _scan(tmp_path)
    scan_report = json.loads(scan_out.read_bytes())
    out = tmp_path / "report.json"
    assert main(["report", "--input", str(scan_out), "--out", str(out)]) == 0
    report = json.loads(out.read_bytes())
    _validate(report)
    assert report["predicate"]["kind"] == "mmqa.report"
    assert report["subject"] == scan_report["subject"]
    scan_sha = hashlib.sha256(scan_out.read_bytes()).hexdigest()
    assert report["predicate"]["inputs"] == [{"name": "scan.json", "digest": {"sha256": scan_sha}}]
    assert report["predicate"]["summary"]["unique_content_count"] == 2


def test_diff_is_envelope_with_both_scans_as_inputs(tmp_path: Path) -> None:
    _, s1 = _scan(tmp_path)
    root = tmp_path / "ds"
    (root / "d.txt").write_bytes(b"new")
    s2 = tmp_path / "scan2.json"
    assert main(["scan", "--root", str(root), "--out", str(s2)]) == 0
    out = tmp_path / "diff.json"
    assert main(["diff", "--old", str(s1), "--new", str(s2), "--out", str(out)]) == 0
    report = json.loads(out.read_bytes())
    _validate(report)
    pred = report["predicate"]
    assert pred["kind"] == "mmqa.diff"
    assert [i["name"] for i in pred["inputs"]] == ["scan.json", "scan2.json"]
    assert pred["summary"]["added_file_count"] == 1
    assert pred["details"]["added_files"] == ["d.txt"]
    assert report["subject"] == json.loads(s2.read_bytes())["subject"]


def test_report_rejects_envelope_of_another_kind(tmp_path: Path) -> None:
    _, scan_out = _scan(tmp_path)
    rep = tmp_path / "report.json"
    assert main(["report", "--input", str(scan_out), "--out", str(rep)]) == 0
    # A report envelope is not a scan.
    assert main(["report", "--input", str(rep)]) == 2


def test_spec_documents_are_committed() -> None:
    assert (ROOT / "docs" / "report-envelope.md").is_file()
    assert SCHEMA["properties"]["_type"]["const"] == STATEMENT_TYPE
