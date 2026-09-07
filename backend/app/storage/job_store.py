"""Jobverwaltung auf dem Dateisystem.

Jeder Job bekommt ein eigenes UUID-Verzeichnis. Der Jobstatus wird atomar
geschrieben (temporaere Datei plus ``os.replace``), damit ein gleichzeitig
lesender Request niemals halbe Daten sieht.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from app.models.config import ProjectConfig
from app.models.job import Artifacts, Job, JobStatus
from app.utils.filenames import ensure_within, safe_job_id

logger = logging.getLogger(__name__)

STATE_FILENAME = "job.json"

ARTIFACT_FILES: dict[str, str] = {
    "project": "project.json",
    "cleaned_png": "cleaned.png",
    "toolpath_png": "toolpath.png",
    "simulation_png": "simulation.png",
    "step": "model.step",
    "stl": "model.stl",
    "report": "report.json",
}

DOWNLOAD_MEDIA_TYPES: dict[str, str] = {
    "project": "application/json",
    "cleaned_png": "image/png",
    "toolpath_png": "image/png",
    "simulation_png": "image/png",
    "step": "model/step",
    "stl": "model/stl",
    "report": "application/json",
}


class JobNotFound(KeyError):
    """Der Job existiert nicht oder wurde bereits geloescht."""


class JobStore:
    """Dateibasierter Jobspeicher mit prozessweitem Lock."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -- Pfade -------------------------------------------------------------
    def job_dir(self, job_id: str) -> Path:
        checked = safe_job_id(job_id)
        return ensure_within(self.root, self.root / checked)

    def artifact_path(self, job_id: str, artifact: str) -> Path:
        if artifact not in ARTIFACT_FILES:
            raise ValueError(f"Unbekanntes Artefakt: {artifact!r}")
        return self.job_dir(job_id) / ARTIFACT_FILES[artifact]

    def upload_path(self, job_id: str, suffix: str) -> Path:
        safe_suffix = suffix if suffix in {".png", ".jpg", ".webp"} else ".png"
        return self.job_dir(job_id) / f"upload{safe_suffix}"

    def find_upload(self, job_id: str) -> Path:
        directory = self.job_dir(job_id)
        for suffix in (".png", ".jpg", ".webp"):
            candidate = directory / f"upload{suffix}"
            if candidate.exists():
                return candidate
        raise JobNotFound(f"Zu Job {job_id} existiert keine Bilddatei.")

    # -- Lebenszyklus ------------------------------------------------------
    def create(self, config: ProjectConfig) -> Job:
        job_id = str(uuid.uuid4())
        directory = self.root / job_id
        directory.mkdir(parents=True, exist_ok=False)
        job = Job(job_id=job_id, config=config, warnings=config.warnings())
        self.save(job)
        return job

    def save(self, job: Job) -> None:
        job.touch()
        directory = self.job_dir(job.job_id)
        if not directory.exists():
            raise JobNotFound(f"Jobverzeichnis fuer {job.job_id} fehlt.")
        payload = job.model_dump_json(indent=2)
        with self._lock:
            descriptor, temp_name = tempfile.mkstemp(dir=directory, prefix=".job-", suffix=".tmp")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, directory / STATE_FILENAME)
            except OSError:
                Path(temp_name).unlink(missing_ok=True)
                raise

    def get(self, job_id: str) -> Job:
        state = self.job_dir(job_id) / STATE_FILENAME
        if not state.exists():
            raise JobNotFound(f"Job {job_id} ist unbekannt.")
        try:
            return Job.model_validate_json(state.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise JobNotFound(f"Jobstatus von {job_id} ist unlesbar: {exc}") from exc

    def update(self, job_id: str, **fields) -> Job:
        job = self.get(job_id)
        for key, value in fields.items():
            if not hasattr(job, key):
                raise ValueError(f"Job hat kein Feld {key!r}.")
            setattr(job, key, value)
        self.save(job)
        return job

    def set_progress(self, job_id: str, progress: float, stage: str, message: str) -> Job:
        return self.update(
            job_id,
            status=JobStatus.processing,
            progress=round(min(max(progress, 0.0), 1.0), 3),
            stage=stage,
            message=message,
        )

    def mark_failed(self, job_id: str, error: str) -> Job:
        logger.error("Job %s ist fehlgeschlagen: %s", job_id, error)
        return self.update(
            job_id,
            status=JobStatus.failed,
            error=error,
            stage="failed",
            message="Die Verarbeitung ist fehlgeschlagen.",
        )

    def refresh_artifacts(self, job_id: str) -> Artifacts:
        directory = self.job_dir(job_id)
        present = {
            key: (directory / filename).exists() and (directory / filename).stat().st_size > 0
            for key, filename in ARTIFACT_FILES.items()
        }
        return Artifacts(**present)

    def delete(self, job_id: str) -> None:
        directory = self.job_dir(job_id)
        if not directory.exists():
            raise JobNotFound(f"Job {job_id} ist unbekannt.")
        shutil.rmtree(directory)

    def list_job_ids(self) -> list[str]:
        return sorted(entry.name for entry in self.root.iterdir() if entry.is_dir())

    def cleanup_expired(self, retention_seconds: int) -> int:
        """Loescht Jobverzeichnisse, die aelter als die Aufbewahrungsfrist sind."""
        if retention_seconds <= 0:
            return 0
        cutoff = time.time() - retention_seconds
        removed = 0
        for entry in self.root.iterdir():
            if not entry.is_dir():
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry)
                    removed += 1
            except OSError as exc:
                logger.warning("Jobverzeichnis %s konnte nicht geloescht werden: %s", entry, exc)
        return removed


def write_project_file(path: Path, config: ProjectConfig) -> None:
    """Schreibt die Projektdatei im versionierten JSON-Format."""
    path.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
