"""Audio normalization with ffmpeg → 16 kHz mono WAV."""

from __future__ import annotations

from pathlib import Path


def normalize(src: Path, dst: Path) -> float:
    """Normalize `src` to a 16 kHz mono WAV at `dst`. Return duration in seconds."""
    raise NotImplementedError
