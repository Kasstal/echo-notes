"""faster-whisper wrapper. Load the model once per process, not per job."""

from __future__ import annotations

import threading
from pathlib import Path

from .. import config
from .types import Word

SAMPLE_RATE = 16_000
# A stretch of detected speech at least this long with no recognized words was skipped by the
# first pass.
MIN_GAP_SECONDS = 1.0

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
    """Stretches (seconds) inside speech spans with no recognized words, at least MIN_GAP_SECONDS long."""
    ordered = sorted(words, key=lambda w: w["start"])
    gaps = []
    for start, end in spans:
        cursor = start
        for w in ordered:
            if w["end"] <= start or w["start"] >= end:
                continue
            if w["start"] - cursor >= MIN_GAP_SECONDS:
                gaps.append((cursor, w["start"]))
            cursor = max(cursor, w["end"])
        if end - cursor >= MIN_GAP_SECONDS:
            gaps.append((cursor, end))
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
    # clip: two of three English replies were missing). Re-transcribe just the word-less stretches,
    # each with its own language detection. Looking for gaps between words rather than at whole
    # VAD spans matters: with the short pauses of a real conversation, VAD merges replies in both
    # languages into one span that looks mostly covered.
    spans = [
        (s["start"] / SAMPLE_RATE, s["end"] / SAMPLE_RATE)
        for s in get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=500))
    ]
    for start, end in uncovered_spans(spans, words):
        piece = audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
        # VAD on the piece keeps Whisper from inventing words for a stretch that is only a pause.
        extra, _ = model.transcribe(piece, word_timestamps=True, vad_filter=True)
        words.extend(_words(extra, offset=start))

    words.sort(key=lambda w: w["start"])
    return info.language, words
