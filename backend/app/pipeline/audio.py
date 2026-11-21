"""Audio normalization with ffmpeg → 16 kHz mono WAV."""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

SAMPLE_RATE = 16000


def normalize(src: Path, dst: Path) -> float:
    """Normalize `src` to a 16 kHz mono WAV at `dst`. Return duration in seconds."""
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        raise FileNotFoundError(f"input file not found: {src}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found on PATH; install it (e.g. `brew install ffmpeg`)")

    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-5:]
        raise RuntimeError(f"ffmpeg could not decode {src.name}: " + " | ".join(tail))

    with wave.open(str(dst), "rb") as w:
        frames = w.getnframes()
    if frames == 0:
        raise RuntimeError(f"{src.name} contains no audio")
    return frames / SAMPLE_RATE
