"""Summarize a transcript with the Claude API into summary.json content."""

from __future__ import annotations

import json
import re

import anthropic

from .. import config

SUMMARY_KEYS = ("tldr", "key_points", "decisions", "action_items")
MAX_TOKENS = 16_000

SYSTEM_PROMPT = """\
You summarize meeting and lecture transcripts.

The transcript is given as lines of the form "[mm:ss] Speaker: text". It may mix English, \
Kazakh and Russian. Write the summary in the language most of the transcript is in.

Return only a JSON object with exactly these keys, with no prose and no code fences:
{"tldr": "...", "key_points": ["..."], "decisions": ["..."], \
"action_items": [{"owner": "...", "task": "...", "due": null}]}

Rules:
- tldr is one or two sentences.
- Use only information present in the transcript. Do not add outside knowledge.
- If something is unclear or inaudible, leave it out rather than guess.
- decisions lists only what the participants actually agreed on or decided.
- action_items lists only tasks someone actually committed to. owner is the speaker name \
exactly as written in the transcript, or null if it is not clear who committed. due is the \
deadline as stated, or null if none was given.
- Any list may be empty."""

RETRY_NOTE = (
    "\n\nYour previous reply was not valid JSON. Reply with only the JSON object, "
    "no prose and no code fences."
)


class SummaryError(RuntimeError):
    """Summarization failed. The caller keeps the transcript and marks done_with_warnings."""


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


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if not config.ANTHROPIC_MODEL:
        raise SummaryError("ANTHROPIC_MODEL is not set in .env")
    if not config.ANTHROPIC_API_KEY:
        raise SummaryError("ANTHROPIC_API_KEY is not set in .env")
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _call_model(system: str, user: str) -> str:
    client = _get_client()
    try:
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AuthenticationError as e:
        raise SummaryError("Claude API rejected the key; check ANTHROPIC_API_KEY") from e
    except anthropic.NotFoundError as e:
        raise SummaryError(
            f"Claude API does not know model {config.ANTHROPIC_MODEL!r}; check ANTHROPIC_MODEL"
        ) from e
    except anthropic.APIStatusError as e:
        raise SummaryError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise SummaryError(f"Could not reach the Claude API: {e}") from e
    if response.stop_reason == "refusal":
        raise SummaryError("The model declined to summarize this transcript")
    return "".join(block.text for block in response.content if block.type == "text")


def _ask_json(system: str, user: str) -> dict:
    try:
        return parse_summary(_call_model(system, user))
    except SummaryParseError:
        pass
    try:
        return parse_summary(_call_model(system, user + RETRY_NOTE))
    except SummaryParseError as e:
        raise SummaryError(f"Model returned an invalid summary twice: {e}") from e


def summarize(transcript: dict) -> dict:
    """Summarize `transcript` and return summary.json content.

    Raises SummaryError when the API fails or the reply is still invalid after one retry.
    """
    text = format_transcript(transcript)
    if not text:
        return empty_summary()
    return _ask_json(SYSTEM_PROMPT, f"Transcript:\n\n{text}")
