"""pyannote.audio diarization wrapper. Load the pipeline once."""

from __future__ import annotations

from pathlib import Path

from .types import Turn


def diarize(wav: Path, num_speakers: int | None = None) -> list[Turn]:
    """Diarize `wav` into speaker turns `{start, end, speaker}`.

    If `HF_TOKEN` is missing, raise a clear error naming the two models whose
    terms must be accepted on Hugging Face (pyannote/speaker-diarization-3.1,
    pyannote/segmentation-3.0). `num_speakers` (and min/max) may be passed through.
    """
    raise NotImplementedError
