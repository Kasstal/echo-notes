"""SQLModel table, engine, and small storage helpers. Single file db at DATA_DIR/echonotes.db."""

import json
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, select

from . import config

PIPELINE_STAGES = ("normalizing", "transcribing", "diarizing", "summarizing")
TERMINAL_STATUSES = ("done", "done_with_warnings", "failed")
NON_TERMINAL_STATUSES = ("queued", "recording", *PIPELINE_STAGES)
STATUSES = (*NON_TERMINAL_STATUSES, *TERMINAL_STATUSES)

SOURCES = ("upload", "bot")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class MeetingSession(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=new_id, primary_key=True)
    title: str
    source: str
    status: str = Field(index=True)
    error: str | None = None
    has_warnings: bool = False
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
    duration_sec: float | None = None
    meeting_url: str | None = None
    original_filename: str | None = None


_engine: Engine | None = None
_engine_url: str | None = None


def init_db() -> None:
    """Create DATA_DIR, the SQLite database and its tables."""
    global _engine, _engine_url
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.sessions_dir().mkdir(parents=True, exist_ok=True)
    url = config.database_url()
    if _engine is None or _engine_url != url:
        if _engine is not None:
            _engine.dispose()
        _engine = create_engine(url, connect_args={"check_same_thread": False})
        _engine_url = url
    SQLModel.metadata.create_all(_engine)


def get_engine() -> Engine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """A db session whose objects stay readable after commit."""
    with Session(get_engine(), expire_on_commit=False) as s:
        yield s


def create_session(*, title: str, source: str, status: str, session_id: str | None = None,
                   **fields: Any) -> MeetingSession:
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    row = MeetingSession(id=session_id or new_id(), title=title, source=source, status=status, **fields)
    with session_scope() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return row


def get_session(session_id: str) -> MeetingSession | None:
    with session_scope() as s:
        return s.get(MeetingSession, session_id)


def list_sessions() -> list[MeetingSession]:
    with session_scope() as s:
        # rowid breaks ties when two sessions share a clock tick.
        stmt = select(MeetingSession).order_by(MeetingSession.created_at.desc(), text("sessions.rowid DESC"))
        return list(s.exec(stmt).all())


def update_session(session_id: str, **fields: Any) -> MeetingSession | None:
    """Update fields on a session; returns None if it no longer exists."""
    with session_scope() as s:
        row = s.get(MeetingSession, session_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def set_status(session_id: str, status: str, **fields: Any) -> MeetingSession | None:
    """The single writer for status changes after creation."""
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    return update_session(session_id, status=status, **fields)


def delete_session(session_id: str) -> bool:
    with session_scope() as s:
        row = s.get(MeetingSession, session_id)
        if row is None:
            return False
        s.delete(row)
        s.commit()
        return True


def sessions_with_status(statuses: tuple[str, ...]) -> list[MeetingSession]:
    with session_scope() as s:
        stmt = select(MeetingSession).where(MeetingSession.status.in_(statuses))
        return list(s.exec(stmt).all())


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON to a temp file next to `path`, then rename it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # On Windows the rename fails while a reader briefly has the target open; retry a few times.
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.05)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def read_json(path: Path) -> Any | None:
    """Return parsed JSON, or None if the file is missing."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
