"""Summarize a transcript with the Claude API into summary.json content."""

from __future__ import annotations


def summarize(transcript: dict) -> dict:
    """Summarize `transcript` and return summary.json content.

    Format the transcript as `[mm:ss] Speaker N: text` lines using display names.
    Return only JSON matching the summary contract, using only information present
    in the transcript. For long transcripts (> ~60k chars) summarize in chunks and
    then summarize the chunk summaries (map-reduce).
    """
    raise NotImplementedError
