# EchoNotes dashboard

React + Vite + TypeScript, plain CSS. Two pages, switched with the URL hash:

- `#/`: the sessions list, plus the "Upload recording" and "Send bot to Meet link" forms.
- `#/sessions/<id>`: one session. It shows the status stepper, the summary under the
  AI-generated label, and the speaker-colored transcript with rename and search, plus the
  Export Markdown, Retry summary and Delete buttons. `?t=<seconds>` opens the transcript at
  that moment; clicking a timestamp updates it.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check and production build
npm run lint
```

In dev, Vite proxies `/api` to `http://127.0.0.1:8000`, so start the backend first
(`uvicorn app.main:app` in `backend/`). To point the dashboard at another backend, set
`VITE_API_BASE`, e.g. `VITE_API_BASE=http://127.0.0.1:9000 npm run dev`.

## API responses the dashboard expects

Routes are the ones in the MVP spec. Where the spec leaves the response shape open, the
client in `src/api.ts` expects:

| Route | Response |
|---|---|
| `GET /api/sessions` | array of `{id, title, source: "upload" \| "bot", status, created_at (ISO), duration (seconds or null)}` |
| `GET /api/sessions/{id}` | the same fields plus `error`, `transcript` (transcript.json or null) and `summary` (summary.json or null) |
| `POST /api/sessions/upload`, `POST /api/sessions/bot` | `{id, status}` |
| `GET /api/sessions/{id}/search?q=` | `{results: [segment, ...]}` or a bare array of segments |
| `GET /api/sessions/{id}/export?format=md` | the Markdown file, ideally with `Content-Disposition: attachment` |
| `PATCH .../speakers`, `POST .../retry-summary`, `DELETE ...` | any 2xx; the page reloads the session afterwards |

Errors are shown to the user from FastAPI's `{"detail": "..."}` body when present.
