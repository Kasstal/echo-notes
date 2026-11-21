"""pyannote.audio diarization wrapper. Load the pipeline once."""

from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np

from .. import config
from .types import Turn

MODEL_ID = "pyannote/speaker-diarization-3.1"
TERMS_HINT = (
    "Create a Hugging Face token, put it in .env as HF_TOKEN, and accept the model terms for "
    "both pyannote/speaker-diarization-3.1 and pyannote/segmentation-3.0 on huggingface.co."
)

_pipeline = None
_lock = threading.Lock()


def _get_pipeline():
    global _pipeline
    with _lock:
        if _pipeline is None:
            if not config.HF_TOKEN:
                raise RuntimeError("HF_TOKEN is not set. " + TERMS_HINT)
            from pyannote.audio import Pipeline

            try:
                pipeline = Pipeline.from_pretrained(MODEL_ID, use_auth_token=config.HF_TOKEN)
            except Exception as e:
                raise RuntimeError(f"could not load {MODEL_ID}: {e}. {TERMS_HINT}") from e
            # pyannote returns None instead of raising when the gated model is not accessible.
            if pipeline is None:
                raise RuntimeError(f"could not load {MODEL_ID}. {TERMS_HINT}")
            _pipeline = pipeline
        return _pipeline


def _load_wav(wav: Path):
    import torch

    with wave.open(str(wav), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{wav} is not a 16-bit mono WAV; run audio.normalize first")
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    waveform = torch.from_numpy(pcm.astype(np.float32) / 32768.0).unsqueeze(0)
    return {"waveform": waveform, "sample_rate": rate}


def diarize(
    wav: Path,
    num_speakers: int | None = None,
    *,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> list[Turn]:
    """Diarize `wav` into speaker turns `{start, end, speaker}`.

    If `HF_TOKEN` is missing, raise a clear error naming the two models whose
    terms must be accepted on Hugging Face (pyannote/speaker-diarization-3.1,
    pyannote/segmentation-3.0). `num_speakers` (and min/max) may be passed through.
    """
    pipeline = _get_pipeline()
    # Passing the waveform in memory sidesteps torchaudio's file backends, which differ
    # between versions; the WAV is already 16 kHz mono from audio.normalize.
    annotation = pipeline(
        _load_wav(Path(wav)),
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    turns: list[Turn] = [
        {"start": round(float(seg.start), 3), "end": round(float(seg.end), 3), "speaker": str(label)}
        for seg, _, label in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: (t["start"], t["end"]))
    return turns
