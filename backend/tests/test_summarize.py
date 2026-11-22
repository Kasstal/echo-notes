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
