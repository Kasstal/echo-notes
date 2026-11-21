"""FastAPI app: CORS, health check, and (later) the API router and worker startup."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import router as api_router

app = FastAPI(title="EchoNotes")

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


# TODO(M2): include the session routes and start the worker thread once they land.
#   from .worker import start_worker
#   @app.on_event("startup")
#   def _startup() -> None:
#       init_db(); start_worker()
app.include_router(api_router)
