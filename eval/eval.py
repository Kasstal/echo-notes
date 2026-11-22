"""Evaluation: run the real pipeline and report WER and DER.

Per sample reads `audio.*`, `reference.txt` (manual transcript) and
`reference.rttm` (manual speaker turns), runs the pipeline, and writes WER
(jiwer) and DER (pyannote.metrics, collar 0.25 s) to eval/results.md. Never
fabricate numbers: with no reference recordings it reports that and writes
nothing.

Usage, from the repo root with the backend virtualenv active:

    python eval/eval.py [--data-dir eval/data] [--out eval/results.md]
"""

from __future__ import annotations

import argparse
import logging
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import jiwer
from pyannote.core import Annotation, Segment, Timeline
from pyannote.metrics.diarization import DiarizationErrorRate

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app import config  # noqa: E402
from app.pipeline import run  # noqa: E402

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac"}
COLLAR_SEC = 0.25

TEXT_NORM = jiwer.Compose(
    [
        jiwer.ToLowerCase(),
        jiwer.RemovePunctuation(),
        # Word splitting only looks at spaces, so line breaks in reference.txt must go first.
        jiwer.RemoveWhiteSpace(replace_by_space=True),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.ReduceToListOfListOfWords(),
    ]
)


@dataclass
class Sample:
    name: str
    audio: Path
    reference_txt: Path
    reference_rttm: Path


@dataclass
class Result:
    name: str
    language: str = ""
    duration_sec: float = 0.0
    processing_sec: float = 0.0
    ref_speakers: int = 0
    hyp_speakers: int = 0
    wer: float | None = None
    der: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.wer is not None and self.der is not None

    @property
    def speed(self) -> float:
        return self.processing_sec / self.duration_sec if self.duration_sec else 0.0


def find_samples(data_dir: Path) -> list[Sample]:
    """Return every complete sample folder; print what is missing from incomplete ones."""
    samples = []
    for folder in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        audio = [p for p in folder.glob("audio.*") if p.suffix.lower() in AUDIO_EXTS]
        txt = folder / "reference.txt"
        rttm = folder / "reference.rttm"
        missing = [n for n, ok in [("audio.*", audio), ("reference.txt", txt.is_file()),
                                   ("reference.rttm", rttm.is_file())] if not ok]
        if len(missing) == 3:
            continue
        if missing:
            print(f"skipping {folder.name}: missing {', '.join(missing)}")
            continue
        if len(audio) > 1:
            print(f"skipping {folder.name}: more than one audio.* file")
            continue
        samples.append(Sample(folder.name, audio[0], txt, rttm))
    return samples


def load_rttm(path: Path) -> Annotation:
    """Parse speaker turns from an RTTM file into a pyannote Annotation."""
    annotation = Annotation(uri=path.parent.name)
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] != "SPEAKER" or len(parts) < 8:
            raise ValueError(f"{path}:{lineno}: expected 'SPEAKER <file> 1 <start> <dur> <NA> <NA> <name> ...'")
        start, dur = float(parts[3]), float(parts[4])
        if dur <= 0:
            raise ValueError(f"{path}:{lineno}: duration must be positive")
        annotation[Segment(start, start + dur), lineno] = parts[7]
    if not annotation:
        raise ValueError(f"{path}: no SPEAKER lines")
    return annotation


def hypothesis_annotation(transcript: dict, uri: str) -> Annotation:
    annotation = Annotation(uri=uri)
    for i, seg in enumerate(transcript["segments"]):
        if seg["end"] > seg["start"]:
            annotation[Segment(seg["start"], seg["end"]), i] = seg["speaker"]
    return annotation


def trim_audio(src: Path, dst: Path, seconds: float) -> None:
    # References usually cover only the first few minutes of a longer recording, so the
    # pipeline runs on exactly the annotated span; otherwise WER and DER would count
    # everything after it as insertions and false alarms.
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found on PATH; install it (e.g. `brew install ffmpeg`)")
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(src), "-t", f"{seconds:.3f}", "-vn", "-ac", "1", "-ar", "16000", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not trim {src.name}: {proc.stderr.strip()[-300:]}")


def evaluate(sample: Sample, work_root: Path) -> Result:
    """Run the pipeline on one sample and score it against its references."""
    result = Result(sample.name)
    reference = load_rttm(sample.reference_rttm)
    ref_text = sample.reference_txt.read_text(encoding="utf-8")
    if not ref_text.strip():
        raise ValueError(f"{sample.reference_txt} is empty")
    span_end = reference.get_timeline().extent().end
    result.ref_speakers = len(reference.labels())

    work = work_root / sample.name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    clip = work / "clip.wav"
    trim_audio(sample.audio, clip, span_end)

    started = time.perf_counter()
    transcript = run.process(clip, work, lambda s: print(f"  [{sample.name}] {s}"))
    result.processing_sec = time.perf_counter() - started

    result.language = transcript.get("language", "")
    result.duration_sec = float(transcript.get("duration_sec") or span_end)
    result.notes.extend(transcript.get("warnings", []))

    hyp_text = " ".join(seg["text"] for seg in transcript["segments"])
    result.wer = jiwer.wer(ref_text, hyp_text, reference_transform=TEXT_NORM,
                           hypothesis_transform=TEXT_NORM)

    hypothesis = hypothesis_annotation(transcript, sample.name)
    result.hyp_speakers = len([s for s in hypothesis.labels() if s != "UNKNOWN"])
    metric = DiarizationErrorRate(collar=COLLAR_SEC, skip_overlap=False)
    uem = Timeline([Segment(0.0, span_end)])
    result.der = float(metric(reference, hypothesis, uem=uem))
    return result


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def write_results(results: list[Result], out: Path) -> None:
    ok = [r for r in results if r.ok]
    lines = [
        "# Evaluation results",
        "",
        f"Generated by `eval/eval.py` on {datetime.now():%Y-%m-%d %H:%M}. "
        f"ASR: faster-whisper `{config.WHISPER_MODEL}` ({config.WHISPER_DEVICE}, "
        f"{config.WHISPER_COMPUTE_TYPE}); diarization: pyannote/speaker-diarization-3.1.",
        "",
        "- WER: jiwer, lowercase, punctuation stripped.",
        f"- DER: pyannote.metrics, collar {COLLAR_SEC} s, overlapping speech scored; "
        "hypothesis turns are the transcript segments.",
        "- Each sample is evaluated on the span its reference covers (start of the recording "
        "to the end of the last reference turn).",
        "- Speed is processing time divided by audio duration (below 1.0 is faster than real "
        "time). The first sample also includes loading the models.",
        "",
        "| Sample | Language | Audio (min) | Speakers (ref / found) | WER | DER | Processing (s) | Speed | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        notes = "; ".join(n.replace("|", "/") for n in r.notes)
        lines.append(
            f"| {r.name} | {r.language or '—'} | {r.duration_sec / 60:.1f} | "
            f"{r.ref_speakers} / {r.hyp_speakers} | {pct(r.wer)} | {pct(r.der)} | "
            f"{r.processing_sec:.0f} | {r.speed:.2f}× | {notes} |"
        )
    lines.append(
        f"| **Mean ({len(ok)} of {len(results)})** | | "
        f"{statistics.mean(r.duration_sec for r in ok) / 60:.1f} | | "
        f"**{pct(statistics.mean(r.wer for r in ok))}** | "
        f"**{pct(statistics.mean(r.der for r in ok))}** | "
        f"{statistics.mean(r.processing_sec for r in ok):.0f} | "
        f"{statistics.mean(r.speed for r in ok):.2f}× | |"
    )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the pipeline on reference recordings and report WER and DER.")
    parser.add_argument("--data-dir", type=Path, default=REPO / "eval" / "data")
    parser.add_argument("--out", type=Path, default=REPO / "eval" / "results.md")
    parser.add_argument("--work-dir", type=Path, default=REPO / "data" / "eval",
                        help="where pipeline outputs per sample are kept (gitignored)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.data_dir.is_dir():
        print(f"no reference recordings: {args.data_dir} does not exist; nothing written")
        return 1
    samples = find_samples(args.data_dir)
    if not samples:
        print(f"no reference recordings in {args.data_dir} (see eval/README.md); nothing written")
        return 1

    results = []
    for sample in samples:
        print(f"evaluating {sample.name} ({sample.audio.name})")
        try:
            result = evaluate(sample, args.work_dir)
        except Exception as e:
            traceback.print_exc()
            result = Result(sample.name, notes=[f"failed: {e}"])
        results.append(result)
        if result.ok:
            print(f"  WER {pct(result.wer)}  DER {pct(result.der)}  "
                  f"{result.processing_sec:.0f} s for {result.duration_sec:.0f} s of audio")

    if not any(r.ok for r in results):
        print("every sample failed; nothing written")
        return 1
    write_results(results, args.out)
    print(f"wrote {args.out}")
    return 0 if all(r.ok for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
