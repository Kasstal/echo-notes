"""Summarize a transcript with the Claude API into summary.json content."""

from __future__ import annotations

import json
import re

SUMMARY_KEYS = ("tldr", "key_points", "decisions", "action_items")


class SummaryParseError(ValueError):
    """The model's reply is not a usable summary JSON object."""


def empty_summary() -> dict:
    return {"tldr": "", "key_points": [], "decisions": [], "action_items": []}


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _optional_str(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _action_items(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, str):
            item = {"task": item}
        if not isinstance(item, dict):
            continue
        task = _optional_str(item.get("task"))
        if task:
            items.append(
                {
                    "owner": _optional_str(item.get("owner")),
                    "task": task,
                    "due": _optional_str(item.get("due")),
                }
            )
    return items


def parse_summary(text: str) -> dict:
    """Parse a model reply into a dict that matches the summary contract."""
    cleaned = _strip_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Some replies wrap the object in a sentence; try the outermost braces once.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise SummaryParseError("reply contains no JSON object") from None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            raise SummaryParseError(f"invalid JSON: {e}") from None
    if not isinstance(data, dict):
        raise SummaryParseError("reply JSON is not an object")
    if not any(key in data for key in SUMMARY_KEYS):
        raise SummaryParseError("reply JSON has none of the summary keys")
    return {
        "tldr": _optional_str(data.get("tldr")) or "",
        "key_points": _str_list(data.get("key_points")),
        "decisions": _str_list(data.get("decisions")),
        "action_items": _action_items(data.get("action_items")),
    }


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
