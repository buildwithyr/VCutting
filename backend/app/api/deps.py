"""Gemeinsame Abhaengigkeiten der API."""

from __future__ import annotations

from functools import lru_cache

from app.settings import JOBS_DIR
from app.storage.job_store import JobStore


@lru_cache(maxsize=1)
def get_store() -> JobStore:
    """Prozessweiter Jobspeicher."""
    return JobStore(JOBS_DIR)
