"""Reading text records from JSONL, JSON, CSV and plain-text files."""

from __future__ import annotations

from pathlib import Path

import pytest

from toolkit_mmqa.records import RecordError, iter_records, load_records, parse_fields


def test_jsonl_fields_joined_and_ids(tmp_path: Path) -> None:
    p = tmp_path / "d.jsonl"
    p.write_text(
        '{"id": 7, "q": "Question?", "choices": ["a", "b"]}\n\n{"q": "Two", "choices": []}\n',
        encoding="utf-8",
    )
    recs = load_records(p, fields=("q", "choices"), id_field="id")
    assert [(r.index, r.text, r.id) for r in recs] == [
        (0, "Question?\na\nb", "7"),
        (1, "Two\n", None),
    ]


def test_jsonl_with_bom_and_bare_strings(tmp_path: Path) -> None:
    p = tmp_path / "d.jsonl"
    p.write_bytes(b'\xef\xbb\xbf"first"\n"second"\n')
    assert [r.text for r in load_records(p)] == ["first", "second"]


def test_json_array(tmp_path: Path) -> None:
    p = tmp_path / "d.json"
    p.write_text('[{"text": "a"}, {"text": "b"}]', encoding="utf-8")
    assert [r.text for r in load_records(p)] == ["a", "b"]


def test_csv(tmp_path: Path) -> None:
    p = tmp_path / "d.csv"
    p.write_text('text,label\n"hello, world",1\nbye,0\n', encoding="utf-8")
    assert [r.text for r in load_records(p)] == ["hello, world", "bye"]


def test_text_one_record_per_line(tmp_path: Path) -> None:
    p = tmp_path / "d.txt"
    p.write_text("line one\n\nline two\r\n", encoding="utf-8")
    assert [(r.index, r.text) for r in load_records(p)] == [(0, "line one"), (1, "line two")]


def test_missing_field_fails_closed_with_location(tmp_path: Path) -> None:
    p = tmp_path / "d.jsonl"
    p.write_text('{"text": "ok"}\n{"other": "x"}\n', encoding="utf-8")
    with pytest.raises(RecordError, match=r"d.jsonl:2: missing field 'text'"):
        load_records(p)


def test_malformed_json_line_fails_closed(tmp_path: Path) -> None:
    p = tmp_path / "d.jsonl"
    p.write_text('{"text": "ok"}\n{broken\n', encoding="utf-8")
    with pytest.raises(RecordError, match="d.jsonl:2: invalid JSON"):
        list(iter_records(p))


def test_json_must_be_array(tmp_path: Path) -> None:
    p = tmp_path / "d.json"
    p.write_text('{"text": "a"}', encoding="utf-8")
    with pytest.raises(RecordError):
        load_records(p)


def test_parse_fields() -> None:
    assert parse_fields(None) == ("text",)
    assert parse_fields(" q , a ") == ("q", "a")
