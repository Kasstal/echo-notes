# One image: the backend API, the pipeline (ffmpeg, faster-whisper, pyannote) and the built dashboard.
# The Meet bot is not included: it needs a headed Chromium with a signed-in profile on the host.

FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Same uid as a typical Linux host user, so files written to the mounted data/ stay editable there.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# CPU builds of torch first; the default PyPI wheels pull in several GB of CUDA libraries.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY eval/ eval/
COPY --from=frontend /app/frontend/dist frontend/dist
# The model-cache volume copies this folder's owner when it is first created; without it, root owns it.
RUN mkdir -p data /home/app/.cache && chown -R app:app /app/data /home/app/.cache

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
