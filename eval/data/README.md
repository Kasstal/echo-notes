# Eval reference recordings

One folder per sample, each containing:

- `audio.*` — the recording (gitignored)
- `reference.txt` — manual transcript
- `reference.rttm` — manual speaker turns

These are supplied by a human. `eval/eval.py` runs the real pipeline over each
sample and writes WER/DER to `eval/results.md`.
