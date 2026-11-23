"""Build an eval sample folder from an AMI meeting (audio + manual words + RTTM).

The AMI corpus (CC BY 4.0) has manually transcribed, time-aligned words for every
participant, which gives a human reference for both WER and DER. This script cuts a
window of one meeting between two pauses, shifts it to start at 0:00, and writes
`audio.wav`, `reference.txt` and `reference.rttm` in the format `eval/eval.py` expects.

    python eval/ami_sample.py --meeting ES2004a --audio ES2004a.wav \\
        --words-dir ami_public_manual_1.6.2/words --rttm ES2004a.rttm \\
        --out eval/data/ami_es2004a --start 3.5 --minutes 5
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# Hesitations Whisper leaves out; eval/README.md asks references to omit them too.
FILLERS = {"um", "uh", "er", "erm", "eh", "ah", "mm", "hmm", "mm-hmm", "uh-huh", "mm-mm", "uh-uh", "hmm-mm"}


def load_turns(rttm: Path, meeting: str) -> list[tuple[float, float, str]]:
    turns = []
    for line in rttm.read_text().splitlines():
        parts = line.split()
        if parts and parts[0] == "SPEAKER" and parts[1] == meeting:
            start, dur = float(parts[3]), float(parts[4])
            turns.append((start, start + dur, parts[7]))
    return sorted(turns)


def cut_point(turns: list[tuple[float, float, str]], target: float) -> float:
    """First moment at or after `target` when nobody is speaking."""
    end = 0.0
    for start, stop, _ in turns:
        if start > max(end, target):
            break
        end = max(end, stop)
    return max(end, target)


def load_words(words_dir: Path, meeting: str, since: float, until: float) -> list[tuple[float, str]]:
    words = []
    for path in sorted(words_dir.glob(f"{meeting}.*.words.xml")):
        for el in ET.parse(path).getroot():
            if el.tag != "w" or el.get("punc") == "true" or el.get("trunc") == "true":
                continue
            text = (el.text or "").strip()
            start = el.get("starttime")
            if not text or start is None or text.lower() in FILLERS:
                continue
            if since <= float(start) < until:
                words.append((float(start), text))
    return sorted(words)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--words-dir", type=Path, required=True)
    parser.add_argument("--rttm", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start", type=float, default=0.0, help="window start, minutes")
    parser.add_argument("--minutes", type=float, default=5.0, help="window length")
    args = parser.parse_args()

    turns = load_turns(args.rttm, args.meeting)
    if not turns:
        raise SystemExit(f"no turns for {args.meeting} in {args.rttm}")
    # Meetings often open with one person presenting; a later window with real turn-taking
    # says more about diarization. Both ends are moved to a pause so no word is cut.
    since = cut_point(turns, args.start * 60) if args.start else 0.0
    until = cut_point(turns, since + args.minutes * 60)
    kept = [(s - since, e - since, spk) for s, e, spk in turns if since <= s < until]
    words = load_words(args.words_dir, args.meeting, since, until)
    if not words:
        raise SystemExit(f"no words for {args.meeting} in {args.words_dir}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg not found on PATH")
    args.out.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-ss", f"{since:.3f}",
                    "-i", str(args.audio), "-t", f"{until - since:.3f}", "-ac", "1", "-ar", "16000", str(args.out / "audio.wav")],
                   check=True)
    (args.out / "reference.txt").write_text(" ".join(w for _, w in words) + "\n", encoding="utf-8")
    (args.out / "reference.rttm").write_text(
        "".join(f"SPEAKER {args.out.name} 1 {s:.2f} {e - s:.2f} <NA> <NA> {spk} <NA> <NA>\n"
                for s, e, spk in kept)
    )
    print(f"{args.meeting}: {since:.1f}-{until:.1f} s, {len(kept)} turns, "
          f"{len({t[2] for t in kept})} speakers, {len(words)} words -> {args.out}")


if __name__ == "__main__":
    main()
