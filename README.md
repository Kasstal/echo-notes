# EchoNotes

A bot that joins an online lecture or meeting, records it, and produces a
speaker-labeled transcript plus a structured summary. Two entry points:

- **Upload mode** — upload an audio/video file → transcript + diarization + summary.
- **Bot mode (Google Meet)** — paste a Meet link → a Chromium bot joins, records,
  leaves, and runs the same pipeline.


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

Run the pipeline from the CLI (once implemented):

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

The bot runs a **headed** Chromium with a persistent profile at
`bot/profile/` (gitignored). Sign the dedicated bot Google account into that
profile once, by hand, before using bot mode. The account's display name is
`EchoNotes Notetaker (recording)` so participants can see what it is.

```bash
python meet_bot.py --url "<meet-link>" --session-id "<id>"
```

Joining a live call needs a human to create the meeting and admit the bot.

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
