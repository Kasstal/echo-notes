# Eval reference recordings

One folder per sample, each containing:

- `audio.*` — the recording (gitignored)
- `reference.txt` — manual transcript
- `reference.rttm` — manual speaker turns

See `eval/README.md` for how to write the references and run `eval/eval.py`.

## AMI samples (`ami_*`)

Three 5-minute windows from meetings in the AMI Meeting Corpus test set, four participants
each, close-talking microphones mixed to one channel:

| Folder | Meeting | Window in the original |
|---|---|---|
| `ami_es2004a` | ES2004a (Edinburgh) | 3:30–8:39 |
| `ami_ts3003a` | TS3003a (TNO) | 16:15–21:24 |
| `ami_is1009c` | IS1009c (Idiap) | 9:53–15:01 |

The windows were picked for turn-taking between all four speakers rather than the opening
minutes, where one person usually presents alone. Both ends fall on a pause.

- `reference.txt` comes from the corpus's manual word annotations
  (`ami_public_manual_1.6.2`), with punctuation, truncated words and fillers (um, uh,
  mm-hmm, …) left out.
- `reference.rttm` is the speaker-turn reference from
  [pyannote/AMI-diarization-setup](https://github.com/pyannote/AMI-diarization-setup)
  (`only_words` version), shifted to the window.
- The audio is not committed. Rebuild a folder with `eval/ami_sample.py` from the
  `Mix-Headset` recording, the manual annotations and the RTTM (see the script's
  docstring for the command; use the start minutes above).

AMI Meeting Corpus © University of Edinburgh and the AMI consortium, released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Carletta, J. et al. (2005),
*The AMI Meeting Corpus: A Pre-Announcement*, MLMI 2005.
