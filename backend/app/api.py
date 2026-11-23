"""REST routes under /api (see the MVP spec)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, field_validator

from . import config, db, worker
from .db import MeetingSession

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

SESSION_ID_RE = re.compile(r"[0-9a-f]{32}")
EXT_RE = re.compile(r"\.[a-z0-9]{1,10}")
MEET_PREFIX = "https://meet.google.com/"
AI_LABEL = "AI-generated summary — verify against the transcript"
CHUNK = 1024 * 1024

# Bot processes started by this server, keyed by session id.
_bots: dict[str, subprocess.Popen] = {}
_bots_lock = threading.Lock()
# Serializes read-modify-write of transcript.json for speaker renames.
_transcript_lock = threading.Lock()


def _get_or_404(session_id: str) -> MeetingSession:
    if not SESSION_ID_RE.fullmatch(session_id):
        raise HTTPException(404, "Session not found")
    row = db.get_session(session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    return row


def _iso(dt: datetime) -> str:
    # SQLite drops tzinfo; everything is stored in UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _transcript_path(session_id: str) -> Path:
    return config.session_dir(session_id) / "transcript.json"


def _summary_path(session_id: str) -> Path:
    return config.session_dir(session_id) / "summary.json"


def _read_optional_json(path: Path) -> Any | None:
    try:
        return db.read_json(path)
    except (OSError, ValueError):
        log.exception("could not read %s", path)
        return None


def _list_item(row: MeetingSession) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "source": row.source,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "duration_sec": row.duration_sec,
        "error": row.error,
    }


def _metadata(row: MeetingSession) -> dict:
    return {
        **_list_item(row),
        "has_warnings": row.has_warnings,
        "updated_at": _iso(row.updated_at),
        "meeting_url": row.meeting_url,
        "original_filename": row.original_filename,
    }


@router.post("/sessions/upload")
def upload_session(file: UploadFile = File(...), title: str | None = Form(None)) -> dict:
    filename = Path(file.filename or "").name
    ext = Path(filename).suffix.lower()
    if not EXT_RE.fullmatch(ext):
        ext = ""
    session_id = db.new_id()
    sdir = config.session_dir(session_id)
    sdir.mkdir(parents=True, exist_ok=False)
    dst = sdir / f"original{ext}"
    size = 0
    try:
        with open(dst, "wb") as out:
            while chunk := file.file.read(CHUNK):
                out.write(chunk)
                size += len(chunk)
    except Exception:
        shutil.rmtree(sdir, ignore_errors=True)
        raise
    if size == 0:
        shutil.rmtree(sdir, ignore_errors=True)
        raise HTTPException(400, "Uploaded file is empty")

    title = (title or "").strip() or Path(filename).stem or "Untitled recording"
    db.create_session(session_id=session_id, title=title, source="upload", status="queued",
                      original_filename=filename or None)
    worker.enqueue_full(session_id, dst)
    return {"id": session_id, "status": "queued"}


class BotStart(BaseModel):
    meeting_url: str
    title: str | None = None

    @field_validator("meeting_url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(MEET_PREFIX) or len(v) == len(MEET_PREFIX) or any(c.isspace() for c in v):
            raise ValueError(f"meeting_url must be a Google Meet link starting with {MEET_PREFIX}")
        return v


@router.post("/sessions/bot")
def start_bot(body: BotStart) -> dict:
    session_id = db.new_id()
    sdir = config.session_dir(session_id)
    sdir.mkdir(parents=True, exist_ok=False)
    code = body.meeting_url[len(MEET_PREFIX):].split("?")[0].strip("/")
    title = (body.title or "").strip() or f"Google Meet {code}"
    db.create_session(session_id=session_id, title=title, source="bot", status="recording",
                      meeting_url=body.meeting_url)

    cmd = [sys.executable, config.BOT_SCRIPT, "--url", body.meeting_url, "--session-id", session_id]
    # The bot writes its recording under DATA_DIR; pass the resolved path so both sides agree.
    env = {**os.environ, "DATA_DIR": str(config.DATA_DIR), "BACKEND_URL": config.BACKEND_URL}
    try:
        with open(sdir / "session.log", "ab") as log_file:
            proc = subprocess.Popen(cmd, cwd=config.REPO_ROOT, stdout=log_file, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env)
    except OSError as exc:
        error = f"Could not start bot: {worker.describe(exc)}"
        db.set_status(session_id, "failed", error=error)
        raise HTTPException(500, error) from exc

    with _bots_lock:
        _bots[session_id] = proc
    threading.Thread(target=_watch_bot, args=(session_id, proc), name=f"bot-watch-{session_id[:8]}",
                     daemon=True).start()
    return {"id": session_id, "status": "recording"}


def _watch_bot(session_id: str, proc: subprocess.Popen) -> None:
    code = proc.wait()
    with _bots_lock:
        if _bots.get(session_id) is proc:
            del _bots[session_id]
    try:
        row = db.get_session(session_id)
        if row is not None and row.status == "recording":
            error = f"Bot exited with code {code} before finishing; see session.log"
            db.set_status(session_id, "failed", error=error)
            worker.log_to_session(session_id, error)
    except Exception:
        log.exception("bot watcher failed for %s", session_id)


def _stop_bot(session_id: str) -> None:
    with _bots_lock:
        proc = _bots.pop(session_id, None)
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


class BotFinished(BaseModel):
    file_path: str | None = None
    error: str | None = None


@router.post("/sessions/{session_id}/bot-finished")
def bot_finished(session_id: str, body: BotFinished) -> dict:
    row = _get_or_404(session_id)
    if row.status != "recording":
        raise HTTPException(409, f"Session is {row.status}, not recording")

    if body.error and body.error.strip():
        db.set_status(session_id, "failed", error=body.error.strip())
        worker.log_to_session(session_id, f"Bot reported error: {body.error.strip()}")
        return {"id": session_id, "status": "failed"}

    if not body.file_path:
        raise HTTPException(422, "file_path is required when error is not set")
    sdir = config.session_dir(session_id).resolve()
    path = Path(body.file_path)
    if not path.is_absolute():
        path = config.REPO_ROOT / path
    path = path.resolve()
    if not path.is_relative_to(sdir):
        raise HTTPException(422, "file_path must be inside the session folder")
    if not path.is_file():
        raise HTTPException(422, "Recording file does not exist")
    if path.stat().st_size == 0:
        raise HTTPException(422, "Recording file is empty")

    db.set_status(session_id, "queued", error=None)
    worker.log_to_session(session_id, f"Bot finished; recording {path.name}")
    worker.enqueue_full(session_id, path)
    return {"id": session_id, "status": "queued"}


@router.get("/sessions")
def list_sessions() -> list[dict]:
    return [_list_item(row) for row in db.list_sessions()]


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    row = _get_or_404(session_id)
    return {
        **_metadata(row),
        "transcript": _read_optional_json(_transcript_path(session_id)),
        "summary": _read_optional_json(_summary_path(session_id)),
    }


@router.patch("/sessions/{session_id}/speakers")
def rename_speakers(session_id: str, names: dict[str, str] = Body(...)) -> dict[str, str]:
    _get_or_404(session_id)
    if not names:
        raise HTTPException(422, "No speakers given")
    cleaned = {label: name.strip() for label, name in names.items()}
    empty = [label for label, name in cleaned.items() if not name]
    if empty:
        raise HTTPException(422, f"Empty name for: {', '.join(empty)}")

    with _transcript_lock:
        path = _transcript_path(session_id)
        transcript = db.read_json(path)
        if transcript is None:
            raise HTTPException(409, "Transcript is not ready yet")
        speakers = transcript.setdefault("speakers", {})
        unknown = [label for label in cleaned if label not in speakers]
        if unknown:
            raise HTTPException(422, f"Unknown speaker labels: {', '.join(unknown)}")
        speakers.update(cleaned)
        db.write_json_atomic(path, transcript)
    return speakers


@router.get("/sessions/{session_id}/search")
def search_session(session_id: str, q: str = Query("")) -> list[dict]:
    _get_or_404(session_id)
    needle = q.strip().casefold()
    transcript = _read_optional_json(_transcript_path(session_id))
    if not needle or not transcript:
        return []
    speakers = transcript.get("speakers", {})
    return [
        {
            "index": i,
            "start": seg["start"],
            "end": seg["end"],
            "speaker": seg["speaker"],
            "speaker_name": speakers.get(seg["speaker"], seg["speaker"]),
            "text": seg["text"],
        }
        for i, seg in enumerate(transcript.get("segments", []))
        if needle in seg.get("text", "").casefold()
    ]


def format_timestamp(seconds: float) -> str:
    total = int(max(seconds, 0))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None"]


def build_markdown(row: MeetingSession, transcript: dict | None, summary: dict | None) -> str:
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    duration = transcript.get("duration_sec") if transcript else None
    if duration is None:
        duration = row.duration_sec
    lines = [
        f"# {row.title}",
        "",
        f"- Date: {created.strftime('%Y-%m-%d %H:%M')} UTC",
        f"- Source: {'Google Meet bot' if row.source == 'bot' else 'Upload'}",
        f"- Duration: {format_timestamp(duration) if duration is not None else 'unknown'}",
        "",
    ]
    if summary:
        lines += [f"> {AI_LABEL}", "", "## Summary", "", f"**TL;DR:** {summary.get('tldr', '')}", ""]
        lines += ["### Key points", "", *_bullets(summary.get("key_points", [])), ""]
        lines += ["### Decisions", "", *_bullets(summary.get("decisions", [])), ""]
        lines += ["### Action items", ""]
        items = summary.get("action_items", [])
        for item in items:
            owner = item.get("owner") or "Unassigned"
            due = f" (due: {item['due']})" if item.get("due") else ""
            lines.append(f"- **{owner}:** {item.get('task', '')}{due}")
        if not items:
            lines.append("- None")
        lines.append("")
    lines += ["## Transcript", ""]
    if transcript and transcript.get("segments"):
        speakers = transcript.get("speakers", {})
        for seg in transcript["segments"]:
            name = speakers.get(seg["speaker"], seg["speaker"])
            lines += [f"**[{format_timestamp(seg['start'])}] {name}:** {seg['text']}", ""]
    else:
        lines += ["_No transcript yet._", ""]
    return "\n".join(lines)


def _download_name(title: str) -> tuple[str, str]:
    base = re.sub(r'[\\/:*?"<>|\r\n]+', "_", title).strip(" .") or "session"
    ascii_base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" ._") or "session"
    return f"{ascii_base}.md", quote(f"{base}.md")


@router.get("/sessions/{session_id}/export")
def export_session(session_id: str, format: str = Query("md")) -> Response:
    row = _get_or_404(session_id)
    if format != "md":
        raise HTTPException(400, "Only format=md is supported")
    md = build_markdown(row, _read_optional_json(_transcript_path(session_id)),
                        _read_optional_json(_summary_path(session_id)))
    ascii_name, utf8_name = _download_name(row.title)
    return Response(
        content=md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"},
    )


@router.post("/sessions/{session_id}/retry-summary")
def retry_summary(session_id: str) -> dict:
    row = _get_or_404(session_id)
    if row.status not in db.TERMINAL_STATUSES:
        raise HTTPException(409, f"Session is still {row.status}")
    if not _transcript_path(session_id).is_file():
        raise HTTPException(409, "No transcript to summarize")
    db.set_status(session_id, "queued")
    worker.enqueue_summary(session_id)
    return {"id": session_id, "status": "queued"}


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> Response:
    row = _get_or_404(session_id)
    if row.status in db.PIPELINE_STAGES:
        raise HTTPException(409, f"Session is being processed ({row.status}); try again when it finishes")
    if row.status == "recording":
        _stop_bot(session_id)

    def _delete_row() -> None:
        current = db.get_session(session_id)
        if current is not None and current.status in db.PIPELINE_STAGES:
            raise HTTPException(409, f"Session is being processed ({current.status})")
        db.delete_session(session_id)

    if not worker.run_unless_busy(session_id, _delete_row):
        raise HTTPException(409, "Session is being processed; try again when it finishes")

    sdir = config.session_dir(session_id)
    try:
        if sdir.exists():
            shutil.rmtree(sdir)
    except OSError as exc:
        raise HTTPException(500, f"Session removed but its folder could not be deleted: {exc}") from exc
    return Response(status_code=204)
