"""Background job queue and status transitions.

One worker thread drains a queue.Queue so CPU-heavy jobs run one at a time.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config, db
from .pipeline import run, summarize

log = logging.getLogger(__name__)

SUMMARY_KEYS = ("tldr", "key_points", "decisions", "action_items")
INTERRUPTED_ERROR = "Interrupted: server restarted"


@dataclass(frozen=True)
class Job:
    session_id: str
    src: Path | None = None  # None means summary-only

    @property
    def summary_only(self) -> bool:
        return self.src is None


_SENTINEL = object()
_queue: queue.Queue = queue.Queue()
_thread: threading.Thread | None = None

# Held while the worker claims a job and while the API deletes a session, so a queued
# session cannot be deleted at the same moment the worker starts on it.
_claim_lock = threading.Lock()
_current: str | None = None


def start() -> None:
    """Start the single background worker thread (no-op if already running)."""
    global _thread, _queue
    if _thread is not None and _thread.is_alive():
        return
    _queue = queue.Queue()
    _thread = threading.Thread(target=_loop, args=(_queue,), name="echonotes-worker", daemon=True)
    _thread.start()


def start_worker() -> None:
    """Start the single background worker thread."""
    start()


def stop(timeout: float = 10.0) -> None:
    """Ask the worker to exit after its current job and wait for it."""
    global _thread
    if _thread is None:
        return
    _queue.put(_SENTINEL)
    _thread.join(timeout)
    _thread = None


def is_alive() -> bool:
    return _thread is not None and _thread.is_alive()


def wait_idle(timeout: float = 30.0) -> bool:
    """Block until every queued job has finished (queue.join with a timeout). For tests."""
    q = _queue
    deadline = time.monotonic() + timeout
    with q.all_tasks_done:
        while q.unfinished_tasks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            q.all_tasks_done.wait(remaining)
    return True


def enqueue(session_id: str) -> None:
    """Queue a session for the full pipeline, using its uploaded original.* file."""
    enqueue_full(session_id, find_original(session_id))


def enqueue_full(session_id: str, src: Path) -> None:
    """Queue the full pipeline (normalize → transcribe → diarize → summarize) on `src`."""
    _queue.put(Job(session_id, Path(src)))


def enqueue_summary(session_id: str) -> None:
    """Queue a summary-only job that re-runs summarization on the existing transcript."""
    _queue.put(Job(session_id, None))


def find_original(session_id: str) -> Path:
    matches = sorted(config.session_dir(session_id).glob("original*"))
    if not matches:
        raise FileNotFoundError(f"no original file for session {session_id}")
    return matches[0]


def run_unless_busy(session_id: str, fn: Callable[[], None]) -> bool:
    """Run `fn` unless the worker is currently processing `session_id`; returns whether it ran."""
    with _claim_lock:
        if _current == session_id:
            return False
        fn()
        return True


def _can_requeue(row) -> bool:
    # A queued upload never started, and its original file is still on disk.
    if row.status != "queued":
        return False
    try:
        find_original(row.id)
    except FileNotFoundError:
        return False
    return True


def recover_interrupted() -> list[str]:
    """Mark sessions left mid-flight by a previous server process as failed.

    Queued uploads whose original file is still there are left queued for requeue_waiting().
    """
    ids = []
    for row in db.sessions_with_status(db.NON_TERMINAL_STATUSES):
        if _can_requeue(row):
            continue
        db.set_status(row.id, "failed", error=INTERRUPTED_ERROR)
        log_to_session(row.id, f"{INTERRUPTED_ERROR} (was {row.status})")
        ids.append(row.id)
    return ids


def requeue_waiting() -> list[str]:
    """Queue again the uploads that were still waiting when the server stopped. Call after start()."""
    ids = []
    for row in db.sessions_with_status(("queued",)):
        if _can_requeue(row):
            enqueue(row.id)
            log_to_session(row.id, "Queued again after server restart")
            ids.append(row.id)
    return ids


def log_to_session(session_id: str, text: str) -> None:
    """Append a timestamped entry to data/sessions/{id}/session.log, if the folder exists."""
    sdir = config.session_dir(session_id)
    if not sdir.is_dir():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        with open(sdir / "session.log", "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] [worker] {text.rstrip()}\n")
    except OSError:
        log.exception("could not write session.log for %s", session_id)


def describe(exc: BaseException) -> str:
    msg = str(exc).strip()
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


def _loop(q: queue.Queue) -> None:
    global _current
    while True:
        job = q.get()
        try:
            if job is _SENTINEL:
                return
            with _claim_lock:
                if db.get_session(job.session_id) is None:
                    log.info("skipping job for deleted session %s", job.session_id)
                    continue
                _current = job.session_id
            _run_job(job)
        except Exception:
            # Never let one bad job kill the thread.
            log.exception("worker job crashed: %r", job)
            if isinstance(job, Job):
                _fail_safely(job.session_id, traceback.format_exc())
        finally:
            _current = None
            q.task_done()


def _fail_safely(session_id: str, tb: str) -> None:
    try:
        log_to_session(session_id, f"Unexpected worker error:\n{tb}")
        row = db.get_session(session_id)
        if row is not None and row.status not in db.TERMINAL_STATUSES:
            db.set_status(session_id, "failed", error="Unexpected worker error; see session.log")
    except Exception:
        log.exception("could not mark session %s failed", session_id)


def _run_job(job: Job) -> None:
    if job.summary_only:
        _run_summary_only(job.session_id)
    else:
        _run_full(job.session_id, job.src)


def _run_full(session_id: str, src: Path) -> None:
    sdir = config.session_dir(session_id)
    log_to_session(session_id, f"Processing {src.name}")

    def on_status(status: str) -> None:
        if status in db.PIPELINE_STAGES:
            db.set_status(session_id, status)
            log_to_session(session_id, f"Status: {status}")
        else:
            log.warning("ignoring unknown pipeline status %r for %s", status, session_id)

    try:
        transcript = run.process(src, sdir, on_status)
        _check_transcript(transcript)
    except Exception as exc:
        log_to_session(session_id, f"Transcription failed:\n{traceback.format_exc()}")
        db.set_status(session_id, "failed", error=f"Transcription failed: {describe(exc)}")
        return

    transcript_path = sdir / "transcript.json"
    if not transcript_path.exists():
        db.write_json_atomic(transcript_path, transcript)

    duration = transcript.get("duration_sec")
    db.update_session(session_id, duration_sec=float(duration) if duration is not None else None)
    _summarize_and_finish(session_id, transcript)


def _run_summary_only(session_id: str) -> None:
    log_to_session(session_id, "Retrying summary")
    transcript = db.read_json(config.session_dir(session_id) / "transcript.json")
    if transcript is None:
        db.set_status(session_id, "failed", error="Cannot retry summary: transcript.json is missing")
        return
    _summarize_and_finish(session_id, transcript)


def _summarize_and_finish(session_id: str, transcript: dict) -> None:
    warnings = []
    if diarization_fell_back(transcript):
        warnings.append("Speaker diarization failed; all segments are labeled UNKNOWN")

    db.set_status(session_id, "summarizing")
    log_to_session(session_id, "Status: summarizing")
    try:
        summary = summarize.summarize(transcript)
        _check_summary(summary)
        db.write_json_atomic(config.session_dir(session_id) / "summary.json", summary)
    except Exception as exc:
        log_to_session(session_id, f"Summarization failed:\n{traceback.format_exc()}")
        warnings.append(f"Summarization failed: {describe(exc)}")

    if warnings:
        message = "; ".join(warnings)
        db.set_status(session_id, "done_with_warnings", error=message, has_warnings=True)
        log_to_session(session_id, f"Status: done_with_warnings ({message})")
    else:
        db.set_status(session_id, "done", error=None, has_warnings=False)
        log_to_session(session_id, "Status: done")


def diarization_fell_back(transcript: dict) -> bool:
    return any(seg.get("speaker") == "UNKNOWN" for seg in transcript.get("segments", []))


def _check_transcript(transcript: object) -> None:
    if not isinstance(transcript, dict) or not isinstance(transcript.get("segments"), list) \
            or not isinstance(transcript.get("speakers"), dict):
        raise ValueError("pipeline returned a transcript that does not match the contract")


def _check_summary(summary: object) -> None:
    if not isinstance(summary, dict):
        raise ValueError("summary is not a JSON object")
    missing = [k for k in SUMMARY_KEYS if k not in summary]
    if missing:
        raise ValueError(f"summary is missing keys: {', '.join(missing)}")
