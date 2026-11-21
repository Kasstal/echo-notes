"""Align words to speaker turns and merge into segments. Pure logic."""

from __future__ import annotations

from .types import Segment, Turn, Word


def align(words: list[Word], turns: list[Turn]) -> list[Segment]:
    """Assign each word a speaker and merge consecutive words into segments.

    For each word, pick the speaker whose turn overlaps it most; if none overlaps,
    use the nearest turn. Merge consecutive same-speaker words into one segment,
    starting a new segment on speaker change or a pause longer than 1.5 s.
    """
    raise NotImplementedError
