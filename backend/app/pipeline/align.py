"""Align words to speaker turns and merge into segments. Pure logic."""

from __future__ import annotations

from .types import Segment, Turn, Word

UNKNOWN = "UNKNOWN"
MAX_PAUSE_SEC = 1.5


def _speaker_for(word: Word, turns: list[Turn]) -> str:
    # Overlap is summed per speaker, so a word that straddles two short turns of
    # the same person still counts as theirs.
    overlap: dict[str, float] = {}
    for turn in turns:
        amount = min(word["end"], turn["end"]) - max(word["start"], turn["start"])
        if amount > 0:
            overlap[turn["speaker"]] = overlap.get(turn["speaker"], 0.0) + amount
    if overlap:
        return max(overlap, key=overlap.__getitem__)

    def distance(turn: Turn) -> float:
        return max(turn["start"] - word["end"], word["start"] - turn["end"], 0.0)

    return min(turns, key=distance)["speaker"]


def align(words: list[Word], turns: list[Turn]) -> list[Segment]:
    """Assign each word a speaker and merge consecutive words into segments.

    For each word, pick the speaker whose turn overlaps it most; if none overlaps,
    use the nearest turn. Merge consecutive same-speaker words into one segment,
    starting a new segment on speaker change or a pause longer than 1.5 s.
    """
    turns = sorted(turns, key=lambda t: t["start"])
    segments: list[Segment] = []
    prev_end: float | None = None

    for word in sorted(words, key=lambda w: w["start"]):
        # faster-whisper words carry a leading space; normalise so joins are clean.
        text = word["word"].strip()
        if not text:
            continue
        speaker = _speaker_for(word, turns) if turns else UNKNOWN

        last = segments[-1] if segments else None
        paused = prev_end is not None and word["start"] - prev_end > MAX_PAUSE_SEC
        if last is not None and last["speaker"] == speaker and not paused:
            last["text"] += " " + text
            last["end"] = max(last["end"], word["end"])
        else:
            start = word["start"]
            if last is not None:
                # ASR timestamps occasionally overlap by a few ms; keep segments disjoint.
                start = max(start, last["end"])
            segments.append(
                {"start": start, "end": max(start, word["end"]), "speaker": speaker, "text": text}
            )
        prev_end = word["end"] if prev_end is None else max(prev_end, word["end"])

    return segments
