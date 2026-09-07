"""Job-Endpunkte.

Wichtig fuer die Hintergrundverarbeitung: der Upload wird *vor* dem Start des
BackgroundTasks vollstaendig in das Jobverzeichnis geschrieben. Der Task
bekommt nur die Job-ID, niemals ein bereits geschlossenes ``UploadFile``.

Downloads laufen ausschliesslich ueber diese Endpunkte. Interne Dateipfade
verlassen den Server nicht.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from app.api.deps import get_store
from app.models.config import SIMPLIFICATION_PRESETS, ProjectConfig, migrate_project_dict
from app.models.job import Job
from app.services.job_runner import run_job
from app.storage.job_store import (
    DOWNLOAD_MEDIA_TYPES,
    JobNotFound,
    JobStore,
    write_project_file,
)
from app.utils.filenames import safe_slug, upload_suffix
from app.utils.validation import UploadRejected, validate_image_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

HTTP_422 = 422
"""Starlette benennt die Konstante je nach Version unterschiedlich."""


def _error_detail(message: str, exc: ValidationError) -> dict:
    """Validierungsfehler in eine JSON-taugliche Antwort uebersetzen.

    ``include_context`` muss aus bleiben: Pydantic legt bei einem
    ``model_validator`` das urspruengliche Exception-Objekt in den Kontext,
    und das laesst sich nicht serialisieren.
    """
    return {
        "message": message,
        "errors": exc.errors(include_url=False, include_context=False, include_input=False),
    }

DOWNLOAD_EXTENSIONS = {
    "project": ".json",
    "cleaned_png": "-bereinigt.png",
    "toolpath_png": "-bahn.png",
    "simulation_png": "-simulation.png",
    "step": ".step",
    "stl": ".stl",
    "report": "-pruefbericht.json",
}


def parse_config(raw: str | None) -> ProjectConfig:
    """Nimmt die Konfiguration als JSON-String entgegen und validiert sie."""
    if raw is None or not raw.strip():
        return ProjectConfig()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=HTTP_422,
            detail=f"Die Konfiguration ist kein gueltiges JSON: {exc.msg} (Zeile {exc.lineno}).",
        ) from exc

    try:
        return ProjectConfig.model_validate(migrate_project_dict(data))
    except ValidationError as exc:
        raise HTTPException(
            status_code=HTTP_422,
            detail=_error_detail("Die Konfiguration ist ungueltig.", exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc


def _load_job(store: JobStore, job_id: str) -> Job:
    try:
        return store.get(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _artifact_response(
    store: JobStore, job_id: str, artifact: str, missing_hint: str, inline: bool = False
) -> FileResponse:
    job = _load_job(store, job_id)
    path = store.artifact_path(job_id, artifact)
    if not path.exists() or path.stat().st_size == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_hint)

    name = safe_slug(job.config.project.name if job.config else "projekt")
    return FileResponse(
        path,
        media_type=DOWNLOAD_MEDIA_TYPES[artifact],
        filename=f"{name}{DOWNLOAD_EXTENSIONS[artifact]}",
        content_disposition_type="inline" if inline else "attachment",
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=Job)
async def create_job(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="PNG, JPG oder WebP, hoechstens 20 MB."),
    config: str | None = Form(default=None, description="Projektkonfiguration als JSON."),
    store: JobStore = Depends(get_store),
) -> Job:
    """Nimmt Bild und Konfiguration entgegen und startet die Verarbeitung."""
    project_config = parse_config(config)

    data = await image.read()
    await image.close()

    try:
        info = validate_image_bytes(data)
    except UploadRejected as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    job = store.create(project_config)
    suffix = upload_suffix(image.filename, info.image_format)
    store.upload_path(job.job_id, suffix).write_bytes(data)
    write_project_file(store.artifact_path(job.job_id, "project"), project_config)

    job = store.update(
        job.job_id,
        stage="queued",
        message=(
            f"Bild angenommen ({info.width}x{info.height} Pixel, {info.image_format}). "
            "Die Verarbeitung startet."
        ),
        artifacts=store.refresh_artifacts(job.job_id),
    )

    # Erst jetzt, mit vollstaendig gesicherter Datei, geht es in den Hintergrund.
    background_tasks.add_task(run_job, store, job.job_id)
    return job


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, store: JobStore = Depends(get_store)) -> Job:
    return _load_job(store, job_id)


@router.get("/{job_id}/preview/cleaned")
def preview_cleaned(job_id: str, store: JobStore = Depends(get_store)) -> FileResponse:
    return _artifact_response(
        store, job_id, "cleaned_png", "Die bereinigte Vorschau ist noch nicht fertig.", inline=True
    )


@router.get("/{job_id}/preview/toolpath")
def preview_toolpath(job_id: str, store: JobStore = Depends(get_store)) -> FileResponse:
    return _artifact_response(
        store, job_id, "toolpath_png", "Die Bahnvorschau ist noch nicht fertig.", inline=True
    )


@router.get("/{job_id}/preview/simulation")
def preview_simulation(job_id: str, store: JobStore = Depends(get_store)) -> FileResponse:
    return _artifact_response(
        store, job_id, "simulation_png", "Die Fraessimulation ist noch nicht fertig.", inline=True
    )


@router.get("/{job_id}/download/project")
def download_project(job_id: str, store: JobStore = Depends(get_store)) -> FileResponse:
    return _artifact_response(store, job_id, "project", "Es existiert keine Projektdatei.")


@router.get("/{job_id}/download/step")
def download_step(job_id: str, store: JobStore = Depends(get_store)) -> FileResponse:
    return _artifact_response(
        store, job_id, "step", "Es wurde keine STEP-Datei erzeugt. Ist 'output.step' aktiviert?"
    )


@router.get("/{job_id}/download/stl")
def download_stl(job_id: str, store: JobStore = Depends(get_store)) -> FileResponse:
    return _artifact_response(
        store, job_id, "stl", "Es wurde kein STL erzeugt. Ist 'output.stl' aktiviert?"
    )


@router.get("/{job_id}/report")
def get_report(job_id: str, store: JobStore = Depends(get_store)) -> JSONResponse:
    """Der Pruefbericht als JSON-Antwort, nicht als Download."""
    _load_job(store, job_id)
    path = store.artifact_path(job_id, "report")
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Der Pruefbericht ist noch nicht fertig."
        )
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, store: JobStore = Depends(get_store)) -> None:
    try:
        store.delete(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


config_router = APIRouter(prefix="/config", tags=["config"])


@config_router.post("/validate", response_model=ProjectConfig)
def validate_config(payload: dict) -> ProjectConfig:
    """Prueft und normalisiert eine Projektdatei.

    Das Frontend nutzt den Endpunkt beim Import, damit die Vorbelegungen der
    Vereinfachungsstufen serverseitig ergaenzt werden.
    """
    try:
        return ProjectConfig.model_validate(migrate_project_dict(payload))
    except ValidationError as exc:
        raise HTTPException(
            status_code=HTTP_422,
            detail=_error_detail("Die Projektdatei ist ungueltig.", exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc


@config_router.get("/defaults")
def config_defaults() -> dict:
    """Standardkonfiguration und die Vorbelegungen der Vereinfachungsstufen."""
    return {
        "defaults": ProjectConfig().model_dump(mode="json"),
        "simplification_presets": SIMPLIFICATION_PRESETS,
    }
