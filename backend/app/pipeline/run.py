"""Pipeline entry point. CLI: python -m app.pipeline.run <file>"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def process(src: Path, session_dir: Path, on_status: Callable[[str], None]) -> dict:
    """Run the full pipeline on `src`, writing outputs into `session_dir`.

    Normalize → ASR → diarize → align → summarize. Write transcript.json (and
    summary.json) and return the transcript dict. Call `on_status` with each stage
    name as it starts so the worker can update the session status.
    """
    raise NotImplementedError


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m app.pipeline.run <file>", file=sys.stderr)
        raise SystemExit(2)
    src = Path(sys.argv[1])
    session_dir = Path("data/sessions/cli")
    session_dir.mkdir(parents=True, exist_ok=True)
    process(src, session_dir, lambda status: print(status))
