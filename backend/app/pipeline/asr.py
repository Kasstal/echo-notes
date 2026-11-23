"""faster-whisper wrapper. Load the model once per process, not per job."""

from __future__ import annotations

import threading
from pathlib import Path

from .. import config
from .types import Word

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
        return _model


def transcribe(wav: Path) -> tuple[str, list[Word]]:
    """Transcribe `wav` with word timestamps.

    Let the language auto-detect (recordings may mix English, Kazakh and Russian).
    Return the detected language and a flat list of words `{start, end, word}`.
    """
    model = _get_model()
    segments, info = model.transcribe(str(wav), word_timestamps=True, vad_filter=True)

    words: list[Word] = []
    # `segments` is a lazy generator; decoding actually happens in this loop.
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"start": round(float(w.start), 3), "end": round(float(w.end), 3), "word": text})
    return info.language, words
