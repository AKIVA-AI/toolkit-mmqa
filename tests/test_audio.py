"""Basic audio checks: decode errors, truncation, empty files, durations.

Duration is frames / sample rate (the WAV and FLAC definitions). Test files are
generated with a known number of frames, and the stdlib reader's result is
cross-checked against libsndfile (via ``soundfile``) as a reference decoder.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from toolkit_mmqa import audio as audio_mod
from toolkit_mmqa.audio import check_audio, decode_audio
from toolkit_mmqa.cli import main


def _wav(path: Path, frames: int, rate: int = 8000, channels: int = 1) -> Path:
    samples = [
        int(8000 * math.sin(2 * math.pi * 440 * (i // channels) / rate))
        for i in range(frames * channels)
    ]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def _dataset(root: Path) -> Path:
    root.mkdir()
    _wav(root / "one_second.wav", 8000)
    _wav(root / "half_second_stereo.wav", 8000, rate=16000, channels=2)
    good = _wav(root / "full.wav", 4000).read_bytes()
    (root / "truncated.wav").write_bytes(good[: len(good) - 2000])
    (root / "garbage.wav").write_bytes(b"not a riff file at all")
    _wav(root / "empty.wav", 0)
    (root / "notes.txt").write_text("x", encoding="utf-8")
    return root


def test_decode_wave_duration_known_by_construction(tmp_path: Path) -> None:
    info = decode_audio(_wav(tmp_path / "a.wav", 12000, rate=8000, channels=2))
    assert (info.frames, info.sample_rate, info.channels) == (12000, 8000, 2)
    assert info.duration == 1.5


def test_stdlib_and_libsndfile_agree(tmp_path: Path) -> None:
    sf = pytest.importorskip("soundfile")
    p = _wav(tmp_path / "a.wav", 12345, rate=22050)
    ref = sf.info(str(p))
    info = decode_audio(p)
    assert info.frames == ref.frames
    assert info.duration == pytest.approx(ref.duration)


def test_check_audio_finds_corrupt_truncated_and_empty(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "ds")
    result = check_audio(root, [p.name for p in root.iterdir()])
    assert result.checked_count == 6
    corrupt = {c["path"]: c["error"] for c in result.corrupt}
    assert set(corrupt) == {"empty.wav", "garbage.wav", "truncated.wav"}
    assert "truncated" in corrupt["truncated.wav"]
    assert corrupt["empty.wav"] == "no audio frames"
    out = result.to_json()
    assert out["duration"]["total_seconds"] == 2.0  # 1.0 + 0.5 + 0.5
    assert out["duration"]["median_seconds"] == 0.5
    assert out["sample_rates"] == {"16000": 1, "8000": 2}
    assert out["channels"] == {"1": 2, "2": 1}


def test_flac_decoded_with_soundfile(tmp_path: Path) -> None:
    sf = pytest.importorskip("soundfile")
    p = tmp_path / "a.flac"
    sf.write(str(p), [0.1 * math.sin(i / 10) for i in range(4410)], 44100)
    info = decode_audio(p)
    assert (info.frames, info.sample_rate) == (4410, 44100)
    assert info.duration == pytest.approx(0.1)
    broken = tmp_path / "broken.flac"
    broken.write_bytes(p.read_bytes()[:60])
    result = check_audio(tmp_path, ["a.flac", "broken.flac"])
    assert [c["path"] for c in result.corrupt] == ["broken.flac"]


def test_formats_without_the_extra_are_unsupported_not_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audio_mod, "_soundfile", lambda: None)
    (tmp_path / "a.mp3").write_bytes(b"ID3fake")
    _wav(tmp_path / "b.wav", 100)
    result = check_audio(tmp_path, ["a.mp3", "b.wav"])
    assert [u["path"] for u in result.unsupported] == ["a.mp3"]
    assert result.corrupt == []
    assert list(result.files) == ["b.wav"]


def test_cli_scan_audio_checks_and_gate(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "ds")
    out = tmp_path / "scan.json"
    code = main(
        ["scan", "--root", str(root), "--audio-checks", "--fail-on", "corrupt-media"]
        + ["--out", str(out)]
    )
    assert code == 1
    pred = json.loads(out.read_bytes())["predicate"]
    assert pred["summary"]["audio_count"] == 6
    assert pred["summary"]["corrupt_media_count"] == 3
    assert pred["summary"]["audio_total_seconds"] == 2.0
    assert pred["summary"]["failed_checks"] == ["corrupt-media"]
    assert pred["details"]["audio"]["files"]["one_second.wav"]["duration"] == 1.0


def test_cli_corrupt_media_needs_a_media_check(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "ds")
    assert main(["scan", "--root", str(root), "--fail-on", "corrupt-media"]) == 2
