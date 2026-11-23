"""Pipeline entry point. CLI: python -m app.pipeline.run <file>"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from .. import config
from . import align, asr, audio, diarize

log = logging.getLogger(__name__)

UNKNOWN = "UNKNOWN"


def _speaker_names(segments: list[dict]) -> dict[str, str]:
    names: dict[str, str] = {}
    for seg in segments:
        label = seg["speaker"]
        if label in names:
            continue
        names[label] = "Unknown speaker" if label == UNKNOWN else f"Speaker {len(names) + 1}"
    return names


def _write_json(path: Path, data: dict) -> None:
    # Write then rename so a reader polling the session never sees a half-written file.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def process(
    src: Path,
    session_dir: Path,
    on_status: Callable[[str], None],
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> dict:
    """Run normalize → ASR → diarize → align on `src` and write `session_dir/transcript.json`.

    Calls `on_status` with "normalizing", "transcribing" and "diarizing" as each stage starts.
    Summarization is a separate step run by the worker. If diarization fails, every segment
    goes under "UNKNOWN" and the reason is listed in the returned dict's `warnings`, so the
    worker can mark the session done_with_warnings. Other failures raise.
    """
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    wav = session_dir / "audio.wav"
    warnings: list[str] = []

    on_status("normalizing")
    duration = audio.normalize(Path(src), wav)

    on_status("transcribing")
    language, words = asr.transcribe(wav)
    if not words:
        warnings.append("no speech was recognized in the recording")

    on_status("diarizing")
    turns = []
    if words:
        try:
            turns = diarize.diarize(
                wav, num_speakers, min_speakers=min_speakers, max_speakers=max_speakers
            )
        except Exception as e:
            log.exception("diarization failed")
            warnings.append(f"diarization failed, speakers are not labeled: {e}")
        if not turns and not warnings:
            warnings.append("diarization found no speech turns, speakers are not labeled")

    segments = align.align(words, turns)
    transcript = {
        "language": language,
        "duration_sec": round(duration, 2),
        "speakers": _speaker_names(segments),
        "segments": segments,
        "warnings": warnings,
    }
    _write_json(session_dir / "transcript.json", transcript)
    return transcript


def _main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.pipeline.run")
    parser.add_argument("file", type=Path)
    parser.add_argument("--stage", choices=["audio", "asr", "diarize", "all"], default="all")
    parser.add_argument("--out", type=Path, default=config.DATA_DIR / "sessions" / "cli")
    parser.add_argument("--num-speakers", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "audio.wav"

    def timed(label: str, fn):
        t0 = time.perf_counter()
        result = fn()
        print(f"[{label}] {time.perf_counter() - t0:.1f}s")
        return result

    if args.stage == "all":
        last = {"name": None, "t": time.perf_counter()}

        def on_status(name: str) -> None:
            now = time.perf_counter()
            if last["name"]:
                print(f"[{last['name']}] {now - last['t']:.1f}s")
            print(f"-> {name}")
            last.update(name=name, t=now)

        transcript = process(args.file, out, on_status, num_speakers=args.num_speakers)
        print(f"[{last['name']} + align] {time.perf_counter() - last['t']:.1f}s")
        print(f"language={transcript['language']} duration={transcript['duration_sec']}s "
              f"speakers={len(transcript['speakers'])} segments={len(transcript['segments'])}")
        for w in transcript["warnings"]:
            print(f"WARNING: {w}")
        print(f"wrote {out / 'transcript.json'}")
        return

    duration = timed("normalize", lambda: audio.normalize(args.file, wav))
    print(f"wrote {wav} ({duration:.1f}s of audio)")
    if args.stage == "asr":
        language, words = timed("transcribe", lambda: asr.transcribe(wav))
        _write_json(out / "words.json", {"language": language, "words": words})
        print(f"language={language} words={len(words)}")
        print(" ".join(w["word"] for w in words)[:500])
        print(f"wrote {out / 'words.json'}")
    elif args.stage == "diarize":
        turns = timed("diarize", lambda: diarize.diarize(wav, args.num_speakers))
        _write_json(out / "turns.json", {"turns": turns})
        speakers = sorted({t["speaker"] for t in turns})
        print(f"turns={len(turns)} speakers={len(speakers)} {speakers}")
        for t in turns[:10]:
            print(f"  {t['start']:7.2f}-{t['end']:7.2f} {t['speaker']}")
        print(f"wrote {out / 'turns.json'}")


if __name__ == "__main__":
    _main()
