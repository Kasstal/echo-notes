"""Shared types for the pipeline modules.

These are the contracts every pipeline stage honors. Keeping them in one place
means asr/diarize/align/summarize/run all agree on the shape of the data they
pass around (see the MVP spec).
"""

from __future__ import annotations

from typing import TypedDict


class Word(TypedDict):
    start: float
    end: float
    word: str


class Turn(TypedDict):
    start: float
    end: float
    speaker: str


class Segment(TypedDict):
    start: float
    end: float
    speaker: str
    text: str
