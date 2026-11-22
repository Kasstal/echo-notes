"""Summarize a transcript with the Claude API into summary.json content."""

from __future__ import annotations


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _display_name(label: str, speakers: dict) -> str:
    if speakers.get(label):
        return speakers[label]
    if label == "UNKNOWN":
        return "Unknown speaker"
    return label


def format_transcript(transcript: dict) -> str:
    """Render segments as `[mm:ss] Name: text` lines using display names."""
    speakers = transcript.get("speakers") or {}
    lines = []
    for seg in transcript.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        name = _display_name(seg.get("speaker") or "UNKNOWN", speakers)
        lines.append(f"[{_timestamp(seg.get('start') or 0)}] {name}: {text}")
    return "\n".join(lines)


def summarize(transcript: dict) -> dict:
    """Summarize `transcript` and return summary.json content.

    Format the transcript as `[mm:ss] Speaker N: text` lines using display names.
    Return only JSON matching the summary contract, using only information present
    in the transcript. For long transcripts (> ~60k chars) summarize in chunks and
    then summarize the chunk summaries (map-reduce).
    """
    raise NotImplementedError
