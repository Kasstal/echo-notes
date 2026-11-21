"""faster-whisper wrapper. Load the model once per process, not per job."""

from __future__ import annotations

from pathlib import Path

from .types import Word


def transcribe(wav: Path) -> tuple[str, list[Word]]:
    """Transcribe `wav` with word timestamps.

    Let the language auto-detect (recordings may mix English, Kazakh and Russian).
    Return the detected language and a flat list of words `{start, end, word}`.
    """
    raise NotImplementedError
