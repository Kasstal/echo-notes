"""faster-whisper wrapper. Load the model once per process, not per job."""

from __future__ import annotations

import threading
from pathlib import Path

from .. import config
from .types import Word

SAMPLE_RATE = 16_000
# A speech span this long with less than this share covered by words was skipped by the first pass.
MIN_GAP_SECONDS = 1.0
MAX_GAP_COVERAGE = 0.3

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


def _words(segments, offset: float = 0.0) -> list[Word]:
    words: list[Word] = []
    # `segments` is a lazy generator; decoding actually happens in this loop.
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(
                    {"start": round(float(w.start) + offset, 3), "end": round(float(w.end) + offset, 3), "word": text}
                )
    return words


def uncovered_spans(spans: list[tuple[float, float]], words: list[Word]) -> list[tuple[float, float]]:
    """Speech spans (seconds) that are long enough but mostly have no recognized words."""
    gaps = []
    for start, end in spans:
        length = end - start
        if length < MIN_GAP_SECONDS:
            continue
        covered = sum(max(0.0, min(end, w["end"]) - max(start, w["start"])) for w in words)
        if covered / length < MAX_GAP_COVERAGE:
            gaps.append((start, end))
    return gaps


def transcribe(wav: Path) -> tuple[str, list[Word]]:
    """Transcribe `wav` with word timestamps.

    Let the language auto-detect (recordings may mix English, Kazakh and Russian).
    Return the main detected language and a flat list of words `{start, end, word}`.
    """
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    model = _get_model()
    audio = decode_audio(str(wav), sampling_rate=SAMPLE_RATE)
    segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=True, multilingual=True)
    words = _words(segments)

    # Whisper decodes each window in the language it detects at the window's start, so a short
    # reply in another language inside that window is often dropped (tested on a Russian/English
    # clip: two of three English replies were missing). Re-transcribe just those speech spans,
    # each with its own language detection.
    spans = [
        (s["start"] / SAMPLE_RATE, s["end"] / SAMPLE_RATE)
        for s in get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=500))
    ]
    for start, end in uncovered_spans(spans, words):
        piece = audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
        extra, _ = model.transcribe(piece, word_timestamps=True, vad_filter=False)
        words.extend(_words(extra, offset=start))

    words.sort(key=lambda w: w["start"])
    return info.language, words
