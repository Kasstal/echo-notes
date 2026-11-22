import json

import pytest

from app.pipeline import summarize as sm


def _transcript(segments, speakers=None):
    return {
        "language": "en",
        "duration_sec": 100.0,
        "speakers": speakers or {},
        "segments": segments,
    }


def test_format_uses_display_names_and_mm_ss():
    t = _transcript(
        [
            {"start": 0.0, "end": 4.2, "speaker": "SPEAKER_00", "text": "Good morning."},
            {"start": 75.9, "end": 80.0, "speaker": "SPEAKER_01", "text": " Hi there. "},
        ],
        {"SPEAKER_00": "Dr. Boranbayev", "SPEAKER_01": "Speaker 2"},
    )
    assert sm.format_transcript(t) == (
        "[00:00] Dr. Boranbayev: Good morning.\n"
        "[01:15] Speaker 2: Hi there."
    )


def test_format_falls_back_to_label_and_unknown():
    t = _transcript(
        [
            {"start": 3725.0, "end": 3726.0, "speaker": "UNKNOWN", "text": "Hello"},
            {"start": 3727.0, "end": 3728.0, "speaker": "SPEAKER_05", "text": "Yes"},
            {"start": 3729.0, "end": 3730.0, "speaker": "SPEAKER_05", "text": "   "},
        ]
    )
    assert sm.format_transcript(t) == (
        "[62:05] Unknown speaker: Hello\n"
        "[62:07] SPEAKER_05: Yes"
    )


VALID = {
    "tldr": "The team planned the demo.",
    "key_points": ["Upload mode is the demo path"],
    "decisions": ["Record the video on Thursday"],
    "action_items": [{"owner": "Speaker 2", "task": "Write eval script", "due": "Wednesday"}],
}


def test_parse_plain_json():
    assert sm.parse_summary(json.dumps(VALID)) == VALID


@pytest.mark.parametrize(
    "wrapped",
    [
        "```json\n{}\n```",
        "```\n{}\n```",
        "  ```JSON\n{}```  ",
        "Here is the summary:\n{}\nLet me know if you need more.",
    ],
)
def test_parse_strips_code_fences_and_prose(wrapped):
    assert sm.parse_summary(wrapped.replace("{}", json.dumps(VALID))) == VALID


@pytest.mark.parametrize("bad", ["not json at all", "{\"tldr\": ", "[1, 2, 3]", "{\"foo\": 1}", ""])
def test_parse_rejects_invalid(bad):
    with pytest.raises(sm.SummaryParseError):
        sm.parse_summary(bad)


def test_parse_fills_missing_keys_and_normalizes_action_items():
    reply = json.dumps(
        {
            "tldr": "  Short.  ",
            "key_points": ["a", "", 5, " b "],
            "action_items": [
                {"owner": "Speaker 1", "task": "Send slides"},
                {"task": "  "},
                "Book the room",
                42,
            ],
        }
    )
    assert sm.parse_summary(reply) == {
        "tldr": "Short.",
        "key_points": ["a", "b"],
        "decisions": [],
        "action_items": [
            {"owner": "Speaker 1", "task": "Send slides", "due": None},
            {"owner": None, "task": "Book the room", "due": None},
        ],
    }
