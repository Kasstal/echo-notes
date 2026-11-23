"""Configuration loaded from the repo-root .env. Never hard-code or commit secrets."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

# Real environment variables win over .env (override=False).
load_dotenv(REPO_ROOT / ".env", override=False)


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _repo_path(value: str) -> Path:
    # Relative paths in .env are relative to the repo root, not to wherever uvicorn was started.
    p = Path(value)
    return p if p.is_absolute() else REPO_ROOT / p


# Tests reassign DATA_DIR, so always read it through the helpers below at call time.
DATA_DIR = _repo_path(_get("DATA_DIR", "data"))

HOST = _get("HOST", "127.0.0.1")
PORT = int(_get("PORT", "8000"))
CORS_ORIGINS = [o.strip() for o in _get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_MODEL = _get("OPENAI_MODEL")

HF_TOKEN = _get("HF_TOKEN")

WHISPER_MODEL = _get("WHISPER_MODEL", "small")
WHISPER_DEVICE = _get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = _get("WHISPER_COMPUTE_TYPE", "int8")

BOT_SCRIPT = "bot/meet_bot.py"
BOT_PROFILE_DIR = _repo_path(_get("BOT_PROFILE_DIR", "bot/profile"))
BOT_DISPLAY_NAME = _get("BOT_DISPLAY_NAME", "EchoNotes Notetaker (recording)")
BOT_MAX_MINUTES = int(_get("BOT_MAX_MINUTES", "90"))
BACKEND_URL = _get("BACKEND_URL", "http://127.0.0.1:8000")

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def db_path() -> Path:
    """SQLite file; always DATA_DIR/echonotes.db so tests and the server never share a db."""
    return DATA_DIR / "echonotes.db"


def database_url() -> str:
    return f"sqlite:///{db_path().as_posix()}"


def sessions_dir() -> Path:
    return DATA_DIR / "sessions"


def session_dir(session_id: str) -> Path:
    return sessions_dir() / session_id
