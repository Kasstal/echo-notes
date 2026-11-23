import json
import sys

from fastapi.testclient import TestClient

from app import api, config, db, worker
from app.main import app

from .conftest import SUMMARY, make_transcript, wait_for

PIPELINE_SEQUENCE = ["queued", "normalizing", "transcribing", "diarizing", "summarizing", "done"]
MEET_URL = "https://meet.google.com/abc-defg-hij"


def upload(client, content=b"RIFF fake audio bytes", name="lecture.mp3", title=None) -> str:
    data = {"title": title} if title is not None else {}
    r = client.post("/api/sessions/upload", files={"file": (name, content, "audio/mpeg")}, data=data)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
    return r.json()["id"]


def upload_and_wait(client, **kwargs) -> dict:
    sid = upload(client, **kwargs)
    assert worker.wait_idle(10)
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200
    return r.json()


def start_bot(client) -> str:
    r = client.post("/api/sessions/bot", json={"meeting_url": MEET_URL})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "recording"
    return r.json()["id"]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_upload_walks_through_every_status(client, fakes, status_log, data_dir):
    sid = upload(client)
    assert worker.wait_idle(10)

    assert [status for s, status in status_log if s == sid] == PIPELINE_SEQUENCE
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["status"] == "done"
    assert session["error"] is None
    assert session["title"] == "lecture"
    assert session["original_filename"] == "lecture.mp3"
    assert session["duration_sec"] == 3710.0
    assert fakes.process_calls == [data_dir / "sessions" / sid / "original.mp3"]
    assert (data_dir / "sessions" / sid / "original.mp3").read_bytes() == b"RIFF fake audio bytes"


def test_upload_uses_given_title_and_lists_newest_first(client):
    first = upload(client, title="  Lecture 1  ")
    second = upload(client, name="weird name.WAV")
    assert worker.wait_idle(10)

    sessions = client.get("/api/sessions").json()
    assert [s["id"] for s in sessions] == [second, first]
    assert sessions[1]["title"] == "Lecture 1"
    assert sessions[0]["title"] == "weird name"
    assert set(sessions[0]) == {"id", "title", "source", "status", "created_at", "duration_sec", "error"}
    assert (config.session_dir(second) / "original.wav").exists()


def test_get_returns_transcript_and_summary(client):
    session = upload_and_wait(client)
    assert set(session["transcript"]) >= {"language", "duration_sec", "speakers", "segments"}
    assert set(session["transcript"]["segments"][0]) == {"start", "end", "speaker", "text"}
    assert set(session["summary"]) == {"tldr", "key_points", "decisions", "action_items"}
    assert set(session["summary"]["action_items"][0]) == {"owner", "task", "due"}
    assert session["source"] == "upload"
    assert session["has_warnings"] is False


def test_diarization_fallback_marks_warnings(client, fakes):
    fakes.unknown_speakers = True
    session = upload_and_wait(client)
    assert session["status"] == "done_with_warnings"
    assert session["has_warnings"] is True
    assert "diarization" in session["error"].lower()
    assert session["summary"] == SUMMARY


def test_summary_failure_keeps_transcript(client, fakes):
    fakes.summarize_error = RuntimeError("Claude API timed out")
    session = upload_and_wait(client)
    assert session["status"] == "done_with_warnings"
    assert session["error"] == "Summarization failed: RuntimeError: Claude API timed out"
    assert session["summary"] is None
    on_disk = json.loads((config.session_dir(session["id"]) / "transcript.json").read_text(encoding="utf-8"))
    assert on_disk == make_transcript()
    log = (config.session_dir(session["id"]) / "session.log").read_text(encoding="utf-8")
    assert "Traceback" in log and "Claude API timed out" in log


def test_pipeline_failure_marks_failed_and_worker_survives(client, fakes):
    fakes.process_error = RuntimeError("ffmpeg could not decode the file")
    failed = upload_and_wait(client)
    assert failed["status"] == "failed"
    assert failed["error"] == "Transcription failed: RuntimeError: ffmpeg could not decode the file"
    assert failed["transcript"] is None
    assert "Traceback" in (config.session_dir(failed["id"]) / "session.log").read_text(encoding="utf-8")

    fakes.process_error = None
    assert worker.is_alive()
    assert upload_and_wait(client)["status"] == "done"


def test_unimplemented_pipeline_gives_readable_error(client, fakes):
    fakes.process_error = NotImplementedError()
    session = upload_and_wait(client)
    assert session["status"] == "failed"
    assert session["error"] == "Transcription failed: NotImplementedError"


def test_retry_summary_runs_only_summarization(client, fakes, status_log):
    fakes.summarize_error = RuntimeError("rate limited")
    sid = upload_and_wait(client)["id"]
    fakes.summarize_error = None

    r = client.post(f"/api/sessions/{sid}/retry-summary")
    assert r.status_code == 200
    assert r.json() == {"id": sid, "status": "queued"}
    assert worker.wait_idle(10)

    session = client.get(f"/api/sessions/{sid}").json()
    assert session["status"] == "done"
    assert session["error"] is None
    assert session["summary"] == SUMMARY
    assert (config.session_dir(sid) / "summary.json").exists()
    assert len(fakes.process_calls) == 1
    assert len(fakes.summarize_calls) == 2
    assert [s for i, s in status_log if i == sid][-3:] == ["queued", "summarizing", "done"]


def test_retry_keeps_diarization_warning(client, fakes):
    fakes.unknown_speakers = True
    fakes.summarize_error = RuntimeError("rate limited")
    sid = upload_and_wait(client)["id"]
    fakes.summarize_error = None

    assert client.post(f"/api/sessions/{sid}/retry-summary").status_code == 200
    assert worker.wait_idle(10)
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["status"] == "done_with_warnings"
    assert "diarization" in session["error"].lower()
    assert "Summarization" not in session["error"]
    assert session["summary"] == SUMMARY


def test_retry_summary_conflicts(client, fakes):
    fakes.process_error = RuntimeError("boom")
    no_transcript = upload_and_wait(client)["id"]
    assert client.post(f"/api/sessions/{no_transcript}/retry-summary").status_code == 409

    fakes.process_error = None
    busy = upload_and_wait(client)["id"]
    db.set_status(busy, "summarizing")
    assert client.post(f"/api/sessions/{busy}/retry-summary").status_code == 409


def test_rename_speakers(client):
    sid = upload_and_wait(client)["id"]
    path = config.session_dir(sid) / "transcript.json"
    segments_before = json.loads(path.read_text(encoding="utf-8"))["segments"]

    r = client.patch(f"/api/sessions/{sid}/speakers", json={"SPEAKER_00": "  Dr. Boranbayev "})
    assert r.status_code == 200
    assert r.json() == {"SPEAKER_00": "Dr. Boranbayev", "SPEAKER_01": "Speaker 2"}
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["speakers"]["SPEAKER_00"] == "Dr. Boranbayev"
    assert after["segments"] == segments_before

    assert client.patch(f"/api/sessions/{sid}/speakers", json={"SPEAKER_09": "Nobody"}).status_code == 422
    assert client.patch(f"/api/sessions/{sid}/speakers", json={"SPEAKER_01": "   "}).status_code == 422
    assert client.patch(f"/api/sessions/{sid}/speakers", json={}).status_code == 422
    assert json.loads(path.read_text(encoding="utf-8"))["speakers"]["SPEAKER_01"] == "Speaker 2"


def test_rename_before_transcript_conflicts(client, fakes):
    fakes.process_error = RuntimeError("boom")
    sid = upload_and_wait(client)["id"]
    assert client.patch(f"/api/sessions/{sid}/speakers", json={"SPEAKER_00": "A"}).status_code == 409


def test_search_is_case_insensitive(client):
    sid = upload_and_wait(client)["id"]
    client.patch(f"/api/sessions/{sid}/speakers", json={"SPEAKER_01": "Aigerim"})

    hits = client.get(f"/api/sessions/{sid}/search", params={"q": "bUdGeT"}).json()
    assert [h["index"] for h in hits] == [0, 1]
    assert hits[1] == {
        "index": 1, "start": 5.0, "end": 9.5, "speaker": "SPEAKER_01", "speaker_name": "Aigerim",
        "text": "I will send the BUDGET draft by Friday.",
    }
    assert client.get(f"/api/sessions/{sid}/search", params={"q": "nothing like this"}).json() == []


def test_search_without_transcript_is_empty(client, fakes):
    fakes.process_error = RuntimeError("boom")
    sid = upload_and_wait(client)["id"]
    r = client.get(f"/api/sessions/{sid}/search", params={"q": "budget"})
    assert r.status_code == 200
    assert r.json() == []


def test_export_markdown(client):
    sid = upload_and_wait(client, title="Budget sync")["id"]
    client.patch(f"/api/sessions/{sid}/speakers", json={"SPEAKER_00": "Dr. Boranbayev"})

    r = client.get(f"/api/sessions/{sid}/export", params={"format": "md"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["content-disposition"].startswith('attachment; filename="Budget sync.md"')
    md = r.text
    assert md.startswith("# Budget sync")
    assert "- Source: Upload" in md
    assert "- Duration: 01:01:50" in md
    assert "AI-generated summary — verify against the transcript" in md
    assert md.index("AI-generated summary") < md.index("**TL;DR:**")
    assert "- Ship the draft this week" in md
    assert "- **Speaker 2:** Send the budget draft (due: Friday)" in md
    assert "**[00:00] Dr. Boranbayev:** Good morning, today we cover the budget." in md
    assert "**[00:05] Speaker 2:** I will send the BUDGET draft by Friday." in md
    assert "**[01:01:40] Dr. Boranbayev:** Thanks everyone." in md

    assert client.get(f"/api/sessions/{sid}/export", params={"format": "pdf"}).status_code == 400


def test_export_without_summary_omits_summary_block(client, fakes):
    fakes.summarize_error = RuntimeError("down")
    sid = upload_and_wait(client)["id"]
    md = client.get(f"/api/sessions/{sid}/export").text
    assert "AI-generated summary" not in md
    assert "TL;DR" not in md
    assert "**[00:00] Speaker 1:**" in md


def test_export_non_ascii_title(client):
    sid = upload_and_wait(client, title="Лекция 1")["id"]
    r = client.get(f"/api/sessions/{sid}/export")
    assert r.status_code == 200
    assert "filename*=UTF-8''%D0%9B" in r.headers["content-disposition"]


def test_format_timestamp():
    assert api.format_timestamp(0) == "00:00"
    assert api.format_timestamp(65.9) == "01:05"
    assert api.format_timestamp(3599) == "59:59"
    assert api.format_timestamp(3600) == "01:00:00"


def test_delete_removes_row_and_folder(client):
    sid = upload_and_wait(client)["id"]
    folder = config.session_dir(sid)
    assert folder.is_dir()

    r = client.delete(f"/api/sessions/{sid}")
    assert r.status_code == 204
    assert not folder.exists()
    assert db.get_session(sid) is None
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 404
    assert client.get("/api/sessions").json() == []


def test_delete_while_processing_conflicts(client):
    sid = upload_and_wait(client)["id"]
    for status in ("normalizing", "transcribing", "diarizing", "summarizing"):
        db.set_status(sid, status)
        assert client.delete(f"/api/sessions/{sid}").status_code == 409
    assert config.session_dir(sid).is_dir()


def test_worker_skips_deleted_session(client, fakes, tmp_path):
    src = tmp_path / "x.wav"
    src.write_bytes(b"x")
    worker.enqueue_full("0" * 32, src)
    assert worker.wait_idle(10)
    assert fakes.process_calls == []
    assert worker.is_alive()


def test_bot_start_launches_subprocess(client, bot_procs):
    sid = start_bot(client)
    assert len(bot_procs) == 1
    proc = bot_procs[0]
    assert proc.args == [sys.executable, "bot/meet_bot.py", "--url", MEET_URL, "--session-id", sid]
    assert proc.kwargs["cwd"] == config.REPO_ROOT
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["status"] == "recording"
    assert session["source"] == "bot"
    assert session["meeting_url"] == MEET_URL
    assert (config.session_dir(sid) / "session.log").exists()


def test_bot_rejects_non_meet_urls(client, bot_procs):
    for url in ("http://meet.google.com/abc", "https://evil.example/meet.google.com/", "https://meet.google.com/"):
        assert client.post("/api/sessions/bot", json={"meeting_url": url}).status_code == 422
    assert bot_procs == []
    assert client.get("/api/sessions").json() == []


def test_bot_finished_with_file_runs_pipeline(client, bot_procs, fakes):
    sid = start_bot(client)
    recording = config.session_dir(sid) / "raw.webm"
    recording.write_bytes(b"webm bytes")

    r = client.post(f"/api/sessions/{sid}/bot-finished", json={"file_path": str(recording), "error": None})
    assert r.status_code == 200
    assert r.json() == {"id": sid, "status": "queued"}
    assert worker.wait_idle(10)
    bot_procs[0].exit(0)

    assert fakes.process_calls == [recording.resolve()]
    assert client.get(f"/api/sessions/{sid}").json()["status"] == "done"
    again = client.post(f"/api/sessions/{sid}/bot-finished", json={"file_path": str(recording)})
    assert again.status_code == 409


def test_bot_finished_with_error_fails(client, bot_procs):
    sid = start_bot(client)
    r = client.post(f"/api/sessions/{sid}/bot-finished", json={"file_path": None, "error": "not admitted"})
    assert r.status_code == 200
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["status"] == "failed"
    assert session["error"] == "not admitted"
    bot_procs[0].exit(0)
    assert client.get(f"/api/sessions/{sid}").json()["error"] == "not admitted"


def test_bot_finished_rejects_bad_files(client, bot_procs, tmp_path):
    sid = start_bot(client)
    outside = tmp_path / "outside.webm"
    outside.write_bytes(b"data")
    empty = config.session_dir(sid) / "raw.webm"
    empty.write_bytes(b"")
    traversal = str(config.session_dir(sid) / ".." / ".." / "outside.webm")

    for body in ({"file_path": str(outside)}, {"file_path": traversal}, {"file_path": str(empty)},
                 {"file_path": str(config.session_dir(sid) / "missing.webm")}, {}):
        assert client.post(f"/api/sessions/{sid}/bot-finished", json=body).status_code == 422, body
    assert client.get(f"/api/sessions/{sid}").json()["status"] == "recording"


def test_bot_finished_on_upload_session_conflicts(client):
    sid = upload_and_wait(client)["id"]
    r = client.post(f"/api/sessions/{sid}/bot-finished", json={"error": "x"})
    assert r.status_code == 409


def test_bot_exit_while_recording_fails(client, bot_procs):
    sid = start_bot(client)
    bot_procs[0].exit(3)
    assert wait_for(lambda: client.get(f"/api/sessions/{sid}").json()["status"] == "failed")
    assert client.get(f"/api/sessions/{sid}").json()["error"] == \
        "Bot exited with code 3 before finishing; see session.log"


def test_delete_while_recording_stops_bot(client, bot_procs):
    sid = start_bot(client)
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert bot_procs[0].terminated
    assert not config.session_dir(sid).exists()
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_invalid_ids_are_404(client):
    sid = upload_and_wait(client)["id"]
    bad_ids = ["abc", sid.upper(), sid + "0", "..", "%2e%2e", "..%2f..%2fetc", "0" * 32]
    for bad in bad_ids:
        assert client.get(f"/api/sessions/{bad}").status_code == 404, bad
        assert client.delete(f"/api/sessions/{bad}").status_code == 404, bad
        assert client.patch(f"/api/sessions/{bad}/speakers", json={"SPEAKER_00": "x"}).status_code == 404, bad
        assert client.get(f"/api/sessions/{bad}/search", params={"q": "a"}).status_code == 404, bad
        assert client.get(f"/api/sessions/{bad}/export").status_code == 404, bad
        assert client.post(f"/api/sessions/{bad}/retry-summary").status_code == 404, bad
        assert client.post(f"/api/sessions/{bad}/bot-finished", json={"error": "x"}).status_code == 404, bad
    assert client.get(f"/api/sessions/{sid}").status_code == 200


def test_empty_upload_is_rejected(client, data_dir):
    r = client.post("/api/sessions/upload", files={"file": ("empty.mp3", b"", "audio/mpeg")})
    assert r.status_code == 400
    assert client.get("/api/sessions").json() == []
    assert list((data_dir / "sessions").iterdir()) == []


def test_startup_recovery_marks_stuck_sessions_failed(data_dir, fakes):
    db.init_db()
    stuck = {status: db.create_session(title=status, source="upload", status=status).id
             for status in db.NON_TERMINAL_STATUSES}
    finished = db.create_session(title="ok", source="upload", status="done").id

    with TestClient(app) as client:
        for status, sid in stuck.items():
            session = client.get(f"/api/sessions/{sid}").json()
            assert session["status"] == "failed", status
            assert session["error"] == "Interrupted: server restarted"
        assert client.get(f"/api/sessions/{finished}").json()["status"] == "done"
    assert fakes.process_calls == []


def test_startup_requeues_waiting_uploads(data_dir, fakes):
    db.init_db()
    waiting = db.create_session(title="waiting", source="upload", status="queued").id
    sdir = config.session_dir(waiting)
    sdir.mkdir(parents=True)
    (sdir / "original.mp3").write_bytes(b"audio")
    lost = db.create_session(title="lost", source="upload", status="queued").id

    with TestClient(app) as client:
        assert worker.wait_idle(10)
        assert client.get(f"/api/sessions/{waiting}").json()["status"] == "done"
        lost_session = client.get(f"/api/sessions/{lost}").json()
        assert lost_session["status"] == "failed"
        assert lost_session["error"] == "Interrupted: server restarted"
    assert [p.name for p in fakes.process_calls] == ["original.mp3"]
