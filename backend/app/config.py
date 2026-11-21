"""Configuration loaded from .env. Never hard-code or commit secrets."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default)


DATA_DIR = Path(_get("DATA_DIR", "data"))
DATABASE_URL = _get("DATABASE_URL", "sqlite:///data/echonotes.db")

HOST = _get("HOST", "127.0.0.1")
PORT = int(_get("PORT", "8000"))
CORS_ORIGINS = [o.strip() for o in _get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _get("ANTHROPIC_MODEL")

HF_TOKEN = _get("HF_TOKEN")

WHISPER_MODEL = _get("WHISPER_MODEL", "small")
WHISPER_DEVICE = _get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = _get("WHISPER_COMPUTE_TYPE", "int8")

BOT_PROFILE_DIR = Path(_get("BOT_PROFILE_DIR", "bot/profile"))
BOT_DISPLAY_NAME = _get("BOT_DISPLAY_NAME", "EchoNotes Notetaker (recording)")
BOT_MAX_MINUTES = int(_get("BOT_MAX_MINUTES", "90"))
BACKEND_URL = _get("BACKEND_URL", "http://127.0.0.1:8000")
