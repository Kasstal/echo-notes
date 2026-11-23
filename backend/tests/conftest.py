import json
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import api, config, db, worker
from app.main import app


def make_transcript(unknown: bool = False) -> dict:
    segments = [
        {"start": 0.0, "end": 4.2, "speaker": "SPEAKER_00", "text": "Good morning, today we cover the budget."},
        {"start": 5.0, "end": 9.5, "speaker": "SPEAKER_01", "text": "I will send the BUDGET draft by Friday."},
        {"start": 3700.0, "end": 3705.0, "speaker": "SPEAKER_00", "text": "Thanks everyone."},
    ]
    speakers = {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "Speaker 2"}
    if unknown:
        segments = [{**seg, "speaker": "UNKNOWN"} for seg in segments]
        speakers = {"UNKNOWN": "Unknown"}
    return {"language": "en", "duration_sec": 3710.0, "speakers": speakers, "segments": segments}


SUMMARY = {
    "tldr": "The team reviewed the budget.",
    "key_points": ["Budget draft is in progress"],
    "decisions": ["Ship the draft this week"],
    "action_items": [{"owner": "Speaker 2", "task": "Send the budget draft", "due": "Friday"}],
}


class FakePipeline:
    """Stands in for run.process and summarize.summarize where the worker calls them."""

    def __init__(self) -> None:
        self.process_calls: list[Path] = []
        self.num_speakers_calls: list[int | None] = []
        self.summarize_calls: list[dict] = []
        self.process_error: Exception | None = None
        self.summarize_error: Exception | None = None
        self.unknown_speakers = False
        self.warnings: list[str] | None = None

    def process(self, src: Path, session_dir: Path, on_status, *, num_speakers: int | None = None) -> dict:
        self.process_calls.append(Path(src))
        self.num_speakers_calls.append(num_speakers)
        if self.process_error is not None:
            raise self.process_error
        for stage in ("normalizing", "transcribing", "diarizing"):
            on_status(stage)
        transcript = make_transcript(unknown=self.unknown_speakers)
        if self.warnings is not None:
            transcript["warnings"] = list(self.warnings)
        (session_dir / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
        return transcript

    def summarize(self, transcript: dict) -> dict:
        self.summarize_calls.append(transcript)
        if self.summarize_error is not None:
            raise self.summarize_error
        return dict(SUMMARY)


class FakePopen:
    """A bot process that keeps "running" until the test calls exit()."""

    def __init__(self, args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.returncode: int | None = None
        self.terminated = False
        self._exited = threading.Event()

    def wait(self, timeout: float | None = None) -> int:
        if not self._exited.wait(timeout):
            raise subprocess.TimeoutExpired(self.args, timeout)
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.exit(1)

    def kill(self) -> None:
        self.exit(1)

    def exit(self, code: int) -> None:
        self.returncode = code
        self._exited.set()


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", d)
    return d


@pytest.fixture
def fakes(monkeypatch) -> FakePipeline:
    fake = FakePipeline()
    monkeypatch.setattr(worker.run, "process", fake.process)
    monkeypatch.setattr(worker.summarize, "summarize", fake.summarize)
    return fake


@pytest.fixture
def status_log(monkeypatch) -> list[tuple[str, str]]:
    """Every status written, in order, as (session_id, status)."""
    calls: list[tuple[str, str]] = []
    real_create, real_set = db.create_session, db.set_status

    def create_spy(**kwargs):
        row = real_create(**kwargs)
        calls.append((row.id, row.status))
        return row

    def set_spy(session_id, status, **kwargs):
        calls.append((session_id, status))
        return real_set(session_id, status, **kwargs)

    monkeypatch.setattr(db, "create_session", create_spy)
    monkeypatch.setattr(db, "set_status", set_spy)
    return calls


@pytest.fixture
def client(data_dir, fakes, status_log):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def bot_procs(monkeypatch):
    procs: list[FakePopen] = []

    def factory(args, **kwargs):
        proc = FakePopen(args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(api.subprocess, "Popen", factory)
    yield procs
    for proc in procs:
        if proc.returncode is None:
            proc.exit(0)


def wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()
