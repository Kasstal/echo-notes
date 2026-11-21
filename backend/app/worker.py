"""Background job queue and status transitions.

One worker thread drains a queue.Queue so CPU-heavy jobs run one at a time.
Stub for M0 — implemented in the Backend milestone (M2).
"""

from __future__ import annotations


def start_worker() -> None:
    """Start the single background worker thread. Implemented in M2."""
    raise NotImplementedError


def enqueue(session_id: str) -> None:
    """Queue a session for processing. Implemented in M2."""
    raise NotImplementedError
