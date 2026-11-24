# EchoNotes

A bot that joins an online lecture or meeting, records it, and produces a
speaker-labeled transcript plus a structured summary. Two entry points:

- **Upload mode** — upload an audio/video file → transcript + diarization + summary.
- **Bot mode (Google Meet)** — paste a Meet link → a Chromium bot joins, records,
  leaves, and runs the same pipeline.


## Run with Docker

The quickest way to run upload mode. One container runs the API, the pipeline and the dashboard.

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY and HF_TOKEN
docker compose up --build -d
```

Open <http://localhost:8000>. Set `ECHONOTES_PORT` to use another host port. The port is
published on localhost only, because there is no login.

- Sessions and the database are written to `./data` on the host. Whisper and pyannote models
  are downloaded on the first job and kept in the `model-cache` volume.
- Run the evaluation inside the container. Mount `eval/` so `results.md` lands on the host:
  `docker compose run --rm -v ./eval:/app/eval echonotes python /app/eval/eval.py`
- Bot mode is not available in the container: the bot needs a headed Chromium with a
  signed-in Google profile, so run it on the host (see section 4 below).
- Stop it with `docker compose down`. Add `-v` to also delete the downloaded models.

## Prerequisites

- Python 3.11
- Node 20+
- ffmpeg (system binary, on `PATH`)

## Setup

### 1. Environment

```bash
cp .env.example .env
```

Fill in `.env`:

- `OPENAI_API_KEY` and `OPENAI_MODEL` — for summarization.
- `HF_TOKEN` — a Hugging Face token for diarization. You must also **accept the
  model terms** on Hugging Face for both:
  - `pyannote/speaker-diarization-3.1`
  - `pyannote/segmentation-3.0`

Secrets live only in `.env`, which is gitignored. Never commit it.

### 2. Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Health check: <http://127.0.0.1:8000/api/health> → `{"status": "ok"}`.

Run the pipeline from the CLI:

```bash
python -m app.pipeline.run path/to/recording.mp3
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens the dashboard at <http://localhost:5173>.

### 4. Bot (Google Meet)

```bash
cd bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

The bot drives an installed **Google Chrome**, headed, with a persistent
profile at `bot/profile/` (gitignored). Google refuses to sign in to
Playwright's bundled Chromium ("This browser or app may not be secure"), and
Meet refuses a signed-out bot ("You can't join this video call"), so Chrome is
the default (`BOT_BROWSER=chrome`). Sign the dedicated bot Google account into
the profile once, by hand. The account's display name is
`EchoNotes Notetaker (recording)` so participants can see what it is.

```bash
python meet_bot.py --setup
```

This opens a plain Chrome window (not driven by Playwright) on Google sign-in;
sign in, then quit Chrome.

```bash
python meet_bot.py --url "<meet-link>" --session-id "<id>"
```

Joining a live call needs a human to create the meeting and admit the bot. The
bot turns its microphone and camera off, joins, and records the other
participants' audio into `data/sessions/<id>/raw.webm` in 5-second slices, so a
crash still leaves the audio recorded so far. It leaves when the call ends, when
it has been the only participant for 60 s, or after `BOT_MAX_MINUTES`, then hands
the recording to the pipeline. If Meet refuses the join or shows a challenge,
the bot stops and the session fails with the text Meet showed; it does not try
to get around Google's checks.
The backend starts the bot with `bot/.venv/bin/python`; set `BOT_PYTHON` in `.env` to use another interpreter.

### 5. Evaluation

Place reference recordings under `eval/data/` (see `eval/data/README.md`), then:

```bash
python eval/eval.py
```

Writes WER/DER to `eval/results.md`.

## Privacy

Audio and outputs live only under `data/`, which is gitignored. Recordings are
never sent anywhere except the configured model APIs, and only the text
transcript goes to the OpenAI API — ASR and diarization run locally.

## Dependencies outside the original stack list

Added during the build, each for a concrete reason: `python-dotenv` (reads `.env`),
`python-multipart` (FastAPI file uploads), pinned `torch`/`torchaudio` and `huggingface_hub<1.0`
plus `matplotlib` and `numpy` (pyannote 3.3 compatibility and direct use in `diarize.py`),
`requests` in the bot, and `oxlint` for linting the frontend. Summarization uses the `openai` SDK.
