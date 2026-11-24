"""pyannote.audio diarization wrapper. Load the pipeline once."""

from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np

from .. import config
from .types import Turn

MODEL_ID = "pyannote/speaker-diarization-3.1"

# pyannote sometimes splits one voice into extra speakers with a second or two of speech each
# (seen on short Zoom recordings with one person talking). On the AMI eval samples, speakers who
# really are different people were at least 0.65 apart (cosine distance between their centroid
# embeddings), so merging below 0.5 and folding in speakers with under a second of speech left
# DER unchanged there while removing the false speakers on the Zoom recordings.
MERGE_DISTANCE = 0.5
MIN_SPEAKER_SEC = 1.0
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
            import torch
            from pyannote.audio import Pipeline
            from pyannote.audio.core.task import Problem, Resolution, Specifications
            from torch.torch_version import TorchVersion

            # torch >= 2.6 loads checkpoints with weights_only=True, which rejects these
            # classes stored in the pyannote 3.x checkpoints. Allow just them instead of
            # turning the check off.
            safe = [TorchVersion, Specifications, Problem, Resolution]
            try:
                with torch.serialization.safe_globals(safe):
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
    annotation, centroids = pipeline(
        _load_wav(Path(wav)),
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        return_embeddings=True,
    )
    turns: list[Turn] = [
        {"start": round(float(seg.start), 3), "end": round(float(seg.end), 3), "speaker": str(label)}
        for seg, _, label in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: (t["start"], t["end"]))
    if num_speakers is None:
        embeddings = {str(label): centroids[i] for i, label in enumerate(annotation.labels())}
        turns = merge_speakers(turns, embeddings, keep_at_least=min_speakers or 1)
    return turns


def merge_speakers(turns: list[Turn], embeddings: dict, keep_at_least: int = 1) -> list[Turn]:
    """Merge speakers whose voices are near-identical, and fold in speakers with almost no speech."""
    speech: dict[str, float] = {}
    for t in turns:
        speech[t["speaker"]] = speech.get(t["speaker"], 0.0) + t["end"] - t["start"]
    centroids = {s: np.asarray(e, dtype=float) for s, e in embeddings.items()
                 if s in speech and np.isfinite(e).all() and np.linalg.norm(e) > 0}
    rename = {s: s for s in speech}

    def distance(a: str, b: str) -> float:
        x, y = centroids[a], centroids[b]
        return float(1 - x @ y / (np.linalg.norm(x) * np.linalg.norm(y)))

    while len(centroids) > keep_at_least:
        pairs = [(distance(a, b), a, b) for i, a in enumerate(centroids) for b in list(centroids)[i + 1:]]
        dist, a, b = min(pairs)
        if dist >= MERGE_DISTANCE:
            short = [s for s in centroids if speech[s] < MIN_SPEAKER_SEC]
            if not short:
                break
            a = min(short, key=speech.get)
            b = min((s for s in centroids if s != a), key=lambda s: distance(a, s))
        keep, drop = (a, b) if speech[a] >= speech[b] else (b, a)
        total = speech[keep] + speech[drop]
        if total > 0:
            centroids[keep] = (centroids[keep] * speech[keep] + centroids[drop] * speech[drop]) / total
        speech[keep] = total
        del centroids[drop]
        for s, target in rename.items():
            if target == drop:
                rename[s] = keep
    return [{**t, "speaker": rename[t["speaker"]]} for t in turns]
