"""In-memory store for background download/transcribe task state."""

from __future__ import annotations

import uuid
from typing import Any

# {job_id: {status, progress, result, error}}
_jobs: dict[str, dict[str, Any]] = {}

DEFAULT_JOB = {
    "status": "pending",
    "progress": None,
    "result": None,
    "error": None,
}


def create_job() -> str:
    """Create a new job and return its UUID."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = dict(DEFAULT_JOB)
    return job_id


def update_job(job_id: str, **kwargs: Any) -> None:
    """Patch any fields on an existing job."""
    if job_id not in _jobs:
        return
    _jobs[job_id].update(kwargs)


def get_job(job_id: str) -> dict | None:
    """Return a snapshot of the job, or None if unknown."""
    job = _jobs.get(job_id)
    if job is None:
        return None
    return dict(job)
