"""Basic audio checks: decode errors, empty files and duration statistics.

PCM WAV files are read with the standard library (:mod:`wave`). Other formats
(FLAC, Ogg Vorbis/Opus, MP3, AIFF, and WAV encodings :mod:`wave` cannot read)
need the optional ``[audio]`` extra (``soundfile``, which bundles libsndfile).
Without it such files are listed as ``unsupported``, not as corrupt.

Every file is decoded to the end, so truncated data is caught: a file whose
decoded frame count is lower than its header declares is corrupt. A file with
no audio frames is also reported as corrupt.
"""

from __future__ import annotations

import wave
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

AUDIO_EXTENSIONS = frozenset({"wav", "flac", "ogg", "oga", "opus", "mp3", "aif", "aiff"})
_BLOCK_FRAMES = 65536


@dataclass(frozen=True)
class AudioInfo:
    frames: int
    sample_rate: int
    channels: int

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0


class UnsupportedAudio(Exception):
    """The file's format needs a decoder that is not installed."""


def _soundfile() -> Any | None:
    try:
        import soundfile
    except (ImportError, OSError):  # OSError: libsndfile missing
        return None
    return soundfile


def _decode_wave(path: Path) -> AudioInfo:
    try:
        with wave.open(str(path), "rb") as w:
            declared = w.getnframes()
            rate, channels = w.getframerate(), w.getnchannels()
            frame_bytes = w.getsampwidth() * channels
            decoded = 0
            while True:
                chunk = w.readframes(_BLOCK_FRAMES)
                if not chunk:
                    break
                decoded += len(chunk) // frame_bytes
    except wave.Error as e:
        if "unknown format" in str(e):
            raise UnsupportedAudio(f"WAV encoding not readable without [audio]: {e}") from e
        raise
    if decoded < declared:
        raise ValueError(f"truncated: header declares {declared} frames, decoded {decoded}")
    return AudioInfo(frames=decoded, sample_rate=rate, channels=channels)


def _decode_soundfile(sf: Any, path: Path) -> AudioInfo:
    info = sf.info(str(path))
    decoded = 0
    for block in sf.blocks(str(path), blocksize=_BLOCK_FRAMES, dtype="int16"):
        decoded += len(block)
    if info.frames > 0 and decoded < info.frames:
        raise ValueError(f"truncated: header declares {info.frames} frames, decoded {decoded}")
    return AudioInfo(frames=decoded, sample_rate=int(info.samplerate), channels=int(info.channels))


def decode_audio(path: Path) -> AudioInfo:
    """Decode *path* completely and return its frame count, rate and channels.

    Raises:
        UnsupportedAudio: The format needs the ``[audio]`` extra.
        Exception: Any decoder error (the file is corrupt).
    """
    sf = _soundfile()
    if path.suffix.lower() == ".wav":
        # The stdlib reader compares the header's frame count with the data,
        # so it catches truncation that libsndfile silently clamps.
        try:
            return _decode_wave(path)
        except UnsupportedAudio:
            if sf is None:
                raise
    if sf is None:
        raise UnsupportedAudio(f"{path.suffix} needs the [audio] extra (soundfile)")
    return _decode_soundfile(sf, path)


@dataclass
class AudioCheckResult:
    """Outcome of :func:`check_audio`."""

    checked_count: int = 0
    corrupt: list[dict[str, str]] = field(default_factory=list)
    unsupported: list[dict[str, str]] = field(default_factory=list)
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        durations = [f["duration"] for f in self.files.values()]
        stats: dict[str, Any] = {}
        if durations:
            stats = {
                "total_seconds": round(sum(durations), 6),
                "min_seconds": round(min(durations), 6),
                "median_seconds": round(median(durations), 6),
                "max_seconds": round(max(durations), 6),
            }
        return {
            "checked_count": self.checked_count,
            "decoded_count": len(self.files),
            "corrupt": self.corrupt,
            "unsupported": self.unsupported,
            "duration": stats,
            "sample_rates": dict(
                sorted(Counter(str(f["sample_rate"]) for f in self.files.values()).items())
            ),
            "channels": dict(
                sorted(Counter(str(f["channels"]) for f in self.files.values()).items())
            ),
            "files": self.files,
        }


def check_audio(root: Path, rel_paths: Iterable[str]) -> AudioCheckResult:
    """Decode every audio file among *rel_paths* (by extension)."""
    result = AudioCheckResult()
    for rel in sorted(rel_paths):
        if Path(rel).suffix.lower().lstrip(".") not in AUDIO_EXTENSIONS:
            continue
        result.checked_count += 1
        try:
            info = decode_audio(root / rel)
        except UnsupportedAudio as e:
            result.unsupported.append({"path": rel, "reason": str(e)})
            continue
        except Exception as e:  # decoders raise many types for bad files
            result.corrupt.append({"path": rel, "error": f"{type(e).__name__}: {e}"})
            continue
        if info.frames == 0:
            result.corrupt.append({"path": rel, "error": "no audio frames"})
            continue
        result.files[rel] = {
            "duration": round(info.duration, 6),
            "frames": info.frames,
            "sample_rate": info.sample_rate,
            "channels": info.channels,
        }
    return result
