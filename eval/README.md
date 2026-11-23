# Evaluation

`eval/eval.py` runs the real pipeline (ffmpeg → faster-whisper → pyannote → alignment) on reference
recordings and measures how close the output is to a manual transcript:

- **WER** (word error rate): substituted, deleted and inserted words divided by the number of words in
  `reference.txt`. Both texts are lowercased, hyphens and dashes become spaces, and the rest of the
  punctuation is stripped.
- **DER** (diarization error rate): the share of reference speech time that is missed, falsely detected,
  or given to the wrong speaker, compared with `reference.rttm`. Boundaries get a 0.25 s collar.
  Speaker names do not have to match; the best mapping is found automatically.
- **Speed**: processing time divided by audio duration (0.5× means a 10-minute recording takes 5 minutes).

Results go to `eval/results.md`, one row per sample plus the mean. Nothing is written when there are
no complete samples.

## Folder format

One folder per recording under `eval/data/`:

```
eval/data/
├── meeting1/
│   ├── audio.m4a          # any of .wav .mp3 .m4a .mp4 .webm .ogg .flac (gitignored)
│   ├── reference.txt
│   └── reference.rttm
└── meeting2/
    └── ...
```

Folders missing one of the three files are skipped with a message. Only record people who agreed to
it. The audio stays local; the annotations are committed.

**Both references must cover the same span, starting at 0:00.** The script trims the audio to the end
of the last turn in `reference.rttm` before running the pipeline, so annotating only the first 5
minutes of a 10-minute meeting is fine, as long as `reference.txt` stops at the same point.

## Writing `reference.txt`

Plain UTF-8 text of exactly what was said, in order, with no speaker names or timestamps. Line breaks
and punctuation do not matter.

- Write words in the language and script they were spoken in (Kazakh and Russian in Cyrillic,
  English in Latin).
- Leave out fillers (um, uh, ээ), because Whisper usually drops them; keep repeated words if they
  were really repeated.
- Write numbers the way Whisper tends to, as digits ("5 minutes", "2026"). A mismatch like "five"
  vs "5" counts as an error.

## Writing `reference.rttm` by hand

RTTM is plain text, one line per speaker turn:

```
SPEAKER meeting1 1 0.00 4.21 <NA> <NA> aibek <NA> <NA>
SPEAKER meeting1 1 4.50 7.80 <NA> <NA> zhangir <NA> <NA>
SPEAKER meeting1 1 11.90 2.35 <NA> <NA> aibek <NA> <NA>
```

| Field | Meaning |
|---|---|
| 1 | always `SPEAKER` |
| 2 | recording name (the folder name is a good choice) |
| 3 | channel, always `1` |
| 4 | turn start, seconds from the beginning |
| 5 | turn **duration** in seconds (not the end time) |
| 6, 7 | `<NA>` |
| 8 | speaker name, one word, the same for every turn of that person |
| 9, 10 | `<NA>` |

- Mark only speech. Leave silences out; pauses shorter than about half a second can stay inside a turn.
- When two people talk at once, write both turns; they may overlap.
- Lines starting with `#` are ignored.

The easiest way to get the times is Audacity: open the recording, select each turn on the waveform,
press Ctrl+B (Cmd+B on macOS) and type the speaker name, then *File → Export → Export Labels*. That
file has `start<TAB>end<TAB>name` per line, and this turns it into RTTM:

```bash
awk -F'\t' '{printf "SPEAKER meeting1 1 %.2f %.2f <NA> <NA> %s <NA> <NA>\n", $1, $2-$1, $3}' labels.txt > reference.rttm
```

## Running

Prerequisites: the backend virtualenv with `backend/requirements.txt` installed, ffmpeg on `PATH`, and
`HF_TOKEN` in `.env` (see the main README). Then, from the repo root:

```bash
python eval/eval.py
```

Options: `--data-dir` (default `eval/data`), `--out` (default `eval/results.md`), `--work-dir`
(default `data/eval`, where each sample's `transcript.json` is kept for inspection).

Exit code 0 means every sample was scored, 2 means some failed (their rows say why), and 1 means
nothing was written. If a row's notes say diarization failed, its DER describes a single "UNKNOWN"
speaker and is not a real diarization result.
