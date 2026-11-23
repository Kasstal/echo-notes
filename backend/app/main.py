"""FastAPI app: CORS, health check, API router, worker lifecycle, and the built frontend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db, worker
from .api import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    worker.recover_interrupted()
    worker.start()
    worker.requeue_waiting()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title="EchoNotes", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(api_router)

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


# Unknown /api paths (e.g. /api/sessions/.. normalized to /api/) must 404, not reach the frontend mount.
@app.api_route("/api", methods=_ALL_METHODS, include_in_schema=False)
@app.api_route("/api/{path:path}", methods=_ALL_METHODS, include_in_schema=False)
def api_not_found(path: str = "") -> None:
    raise HTTPException(404, "Not found")

# Mounted last so it never shadows /api routes.
if config.FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
