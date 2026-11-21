"""Evaluation: run the real pipeline and report WER and DER.

Per sample reads `audio`, `reference.txt` (manual transcript) and
`reference.rttm` (manual speaker turns), runs the pipeline, and writes WER
(jiwer) and DER (pyannote.metrics, collar 0.25 s) to eval/results.md. Never
fabricate numbers: with no reference recordings it reports that and writes
nothing. Stub for M0 — implemented in the Eval milestone (M6).
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("Evaluation is implemented in milestone M6")


if __name__ == "__main__":
    main()
