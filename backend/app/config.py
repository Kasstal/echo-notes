"""Configuration loaded from the repo-root .env. Never hard-code or commit secrets."""

from __future__ import annotations

import os
import sys
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

WHISPER_MODEL = _get("WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = _get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = _get("WHISPER_COMPUTE_TYPE", "int8")

BOT_SCRIPT = "bot/meet_bot.py"
# Playwright lives in the bot's own venv, not in the backend's.
BOT_PYTHON = _get("BOT_PYTHON")
DEFAULT_BOT_PYTHON = "bot/.venv/Scripts/python.exe" if os.name == "nt" else "bot/.venv/bin/python"
BOT_PROFILE_DIR = _repo_path(_get("BOT_PROFILE_DIR", "bot/profile"))
BOT_DISPLAY_NAME = _get("BOT_DISPLAY_NAME", "EchoNotes Notetaker (recording)")
BOT_MAX_MINUTES = int(_get("BOT_MAX_MINUTES", "90"))
BACKEND_URL = _get("BACKEND_URL", "http://127.0.0.1:8000")

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def bot_python() -> str:
    """BOT_PYTHON if set, else the bot venv's python, else the backend's own interpreter."""
    if BOT_PYTHON:
        return str(_repo_path(BOT_PYTHON))
    default = _repo_path(DEFAULT_BOT_PYTHON)
    return str(default) if default.is_file() else sys.executable


def db_path() -> Path:
    """SQLite file; always DATA_DIR/echonotes.db so tests and the server never share a db."""
    return DATA_DIR / "echonotes.db"


def database_url() -> str:
    return f"sqlite:///{db_path().as_posix()}"


def sessions_dir() -> Path:
    return DATA_DIR / "sessions"


def session_dir(session_id: str) -> Path:
    return sessions_dir() / session_id
