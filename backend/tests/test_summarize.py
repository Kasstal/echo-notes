import json
from types import SimpleNamespace

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


class FakeModel:
    """Stands in for _call_model: returns queued replies and records each prompt."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system, user):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        return reply(system, user) if callable(reply) else reply


@pytest.fixture
def fake_model(monkeypatch):
    def install(*replies):
        fake = FakeModel(*replies)
        monkeypatch.setattr(sm, "_call_model", fake)
        return fake

    return install


SHORT = _transcript(
    [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00", "text": "Let's ship upload mode first."},
        {"start": 3.5, "end": 6.0, "speaker": "SPEAKER_01", "text": "I'll write the eval script by Wednesday."},
    ],
    {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "Speaker 2"},
)


def test_summarize_sends_formatted_transcript(fake_model):
    fake = fake_model("```json\n" + json.dumps(VALID) + "\n```")
    assert sm.summarize(SHORT) == VALID
    system, user = fake.calls[0]
    assert system == sm.SYSTEM_PROMPT
    assert "[00:03] Speaker 2: I'll write the eval script by Wednesday." in user


def test_summarize_retries_once_on_invalid_json(fake_model):
    fake = fake_model("Sorry, here it is: {broken", json.dumps(VALID))
    assert sm.summarize(SHORT) == VALID
    assert len(fake.calls) == 2
    assert fake.calls[1][1].endswith(sm.RETRY_NOTE)


def test_summarize_raises_after_second_invalid_reply(fake_model):
    fake = fake_model("nope", "still nope")
    with pytest.raises(sm.SummaryError, match="invalid summary twice"):
        sm.summarize(SHORT)
    assert len(fake.calls) == 2


def test_summarize_empty_transcript_skips_the_api(fake_model):
    fake = fake_model()
    assert sm.summarize(_transcript([])) == sm.empty_summary()
    assert fake.calls == []


@pytest.mark.parametrize("missing", ["ANTHROPIC_MODEL", "ANTHROPIC_API_KEY"])
def test_missing_config_gives_a_clear_error(monkeypatch, missing):
    monkeypatch.setattr(sm.config, "ANTHROPIC_MODEL", "some-model")
    monkeypatch.setattr(sm.config, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(sm.config, missing, "")
    with pytest.raises(sm.SummaryError, match=missing):
        sm.summarize(SHORT)


class FakeClient:
    def __init__(self, response):
        self.messages = self
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _response(stop_reason, *texts):
    blocks = [SimpleNamespace(type="thinking", thinking="")]
    blocks += [SimpleNamespace(type="text", text=t) for t in texts]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(sm.config, "ANTHROPIC_MODEL", "model-from-env")
    monkeypatch.setattr(sm.config, "ANTHROPIC_API_KEY", "test-key")

    def install(response):
        client = FakeClient(response)
        monkeypatch.setattr(sm, "_client", client)
        return client

    return install


def test_call_model_uses_env_model_and_joins_text_blocks(fake_client):
    client = fake_client(_response("end_turn", '{"tldr": ', '"ok"}'))
    assert sm._call_model("sys", "user") == '{"tldr": "ok"}'
    assert client.kwargs["model"] == "model-from-env"
    assert client.kwargs["system"] == "sys"
    assert client.kwargs["messages"] == [{"role": "user", "content": "user"}]


def test_call_model_reports_refusal(fake_client):
    fake_client(_response("refusal"))
    with pytest.raises(sm.SummaryError, match="declined"):
        sm._call_model("sys", "user")


def test_split_chunks_respects_limit_and_line_boundaries():
    lines = [f"[00:{i:02d}] Speaker 1: " + "x" * 20 for i in range(50)]
    text = "\n".join(lines)
    chunks = sm.split_chunks(text, 200)
    assert all(len(c) <= 200 for c in chunks)
    assert "\n".join(chunks) == text
    assert all(line in lines for c in chunks for line in c.split("\n"))


def test_split_chunks_cuts_an_oversized_line():
    chunks = sm.split_chunks("short\n" + "y" * 25, 10)
    assert all(len(c) <= 10 for c in chunks)
    assert "".join(chunks).replace("\n", "") == "short" + "y" * 25


def test_long_transcript_is_summarized_in_chunks(fake_model):
    segments = [
        {"start": i * 5.0, "end": i * 5.0 + 4, "speaker": f"SPEAKER_0{i % 2}", "text": f"Point {i}. " + "words " * 20}
        for i in range(1000)
    ]
    long = _transcript(segments, {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "Speaker 2"})
    text = sm.format_transcript(long)
    assert len(text) > sm.CHUNK_CHARS
    n_chunks = len(sm.split_chunks(text, sm.CHUNK_CHARS))
    assert n_chunks >= 2

    def partial(system, user):
        part = user.split("Transcript part ")[1].split("/")[0]
        return json.dumps({"tldr": f"part {part}", "key_points": [f"kp {part}"], "decisions": [], "action_items": []})

    final = dict(VALID, tldr="Whole meeting.")
    fake = fake_model(*([partial] * n_chunks), "```json\n" + json.dumps(final) + "\n```")

    assert sm.summarize(long) == final
    assert len(fake.calls) == n_chunks + 1
    for system, user in fake.calls[:-1]:
        assert system == sm.SYSTEM_PROMPT
        assert len(user) < sm.CHUNK_CHARS + 200
    reduce_system, reduce_user = fake.calls[-1]
    assert reduce_system == sm.REDUCE_PROMPT
    for part in range(1, n_chunks + 1):
        assert f'"kp {part}"' in reduce_user


def test_chunk_retry_applies_per_call(fake_model, monkeypatch):
    monkeypatch.setattr(sm, "CHUNK_CHARS", 60)
    long = _transcript(
        [{"start": i, "end": i + 1, "speaker": "SPEAKER_00", "text": "a sentence of some length"} for i in range(6)]
    )
    n_chunks = len(sm.split_chunks(sm.format_transcript(long), 60))
    ok = json.dumps(VALID)
    fake = fake_model("garbage", *([ok] * n_chunks), ok)
    assert sm.summarize(long) == VALID
    assert len(fake.calls) == n_chunks + 2
