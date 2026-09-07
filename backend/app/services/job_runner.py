"""Orchestrierung eines Jobs.

Der Runner haelt die Reihenfolge der Pipeline fest und schreibt nach jedem
Schritt den Fortschritt. Er bekommt ausschliesslich die Job-ID; die Bilddaten
liegen zu diesem Zeitpunkt bereits vollstaendig im Jobverzeichnis. Ein bereits
geschlossenes ``UploadFile`` wird bewusst nie an den Hintergrundtask gereicht.
"""

from __future__ import annotations

import json
import logging
import traceback

from app.models.config import ProjectConfig
from app.models.job import JobStatus
from app.models.report import ValidationReport
from app.services.image_cleanup import MotifNotFound, clean_image
from app.services.motif_envelope import build_envelope
from app.services.preview import (
    render_relief_preview,
    render_simulation_preview,
    render_toolpath_preview,
)
from app.services.raster_paths import EmptyToolpath, build_toolpath
from app.services.step_export import StepExportError, export_step
from app.services.step_validation import build_report
from app.services.stl_export import (
    StlExportError,
    build_relief_surface,
    export_plate_stl,
    export_relief_stl,
    validate_stl,
)
from app.services.tone_mapping import place_motif
from app.storage.job_store import JobStore, write_project_file

logger = logging.getLogger(__name__)


class JobFailed(RuntimeError):
    """Verarbeitungsfehler mit einer fuer den Benutzer verstaendlichen Meldung."""


def run_job(store: JobStore, job_id: str) -> None:
    """Fuehrt die vollstaendige Pipeline aus und protokolliert Fehler."""
    try:
        _run(store, job_id)
    except (MotifNotFound, EmptyToolpath, StepExportError, StlExportError, JobFailed) as exc:
        logger.warning("Job %s abgebrochen: %s", job_id, exc)
        store.mark_failed(job_id, str(exc))
    except Exception as exc:  # noqa: BLE001 - letzte Auffanglinie
        logger.exception("Job %s ist unerwartet fehlgeschlagen.", job_id)
        detail = f"{type(exc).__name__}: {exc}"
        logger.debug("Traceback von Job %s:\n%s", job_id, traceback.format_exc())
        store.mark_failed(job_id, f"Unerwarteter Fehler bei der Verarbeitung. {detail}")


def _run(store: JobStore, job_id: str) -> None:
    job = store.get(job_id)
    config = job.config
    if config is None:
        raise JobFailed("Zum Job wurde keine Konfiguration gespeichert.")

    store.set_progress(job_id, 0.05, "reading_upload", "Bilddatei wird gelesen.")
    upload_path = store.find_upload(job_id)
    data = upload_path.read_bytes()

    store.set_progress(job_id, 0.12, "cleanup", "Motiv wird freigestellt und bereinigt.")
    motif = clean_image(data, config.cleanup)

    directory = store.job_dir(job_id)
    motif.save_png(directory / "cleaned.png")

    store.set_progress(job_id, 0.25, "placement", "Motiv wird auf der Platte platziert.")
    raster = place_motif(motif, config)

    warnings = list(config.warnings())
    if config.mode == "relief":
        _run_relief(store, job_id, config, raster, warnings)
        return

    store.set_progress(job_id, 0.35, "envelope", "Motivkontur wird um den Rand erweitert.")
    envelope = build_envelope(raster, config.carving.motif_margin_mm)

    store.set_progress(job_id, 0.45, "toolpath", "Schlangenbahn wird berechnet und vereinfacht.")
    toolpath = build_toolpath(raster, envelope, config)
    metrics = toolpath.metrics(config, raster)

    store.set_progress(job_id, 0.62, "preview", "Vorschaubilder werden gezeichnet.")
    if config.output.preview_png:
        render_toolpath_preview(directory / "toolpath.png", config, raster, envelope, toolpath)
        render_simulation_preview(directory / "simulation.png", config, raster, toolpath)

    step_path = None
    if config.output.step:
        store.set_progress(job_id, 0.75, "step", "STEP-Datei wird erzeugt.")
        step_path = export_step(directory / "model.step", config, toolpath)

    if config.output.stl:
        store.set_progress(job_id, 0.85, "stl", "STL der Referenzplatte wird erzeugt.")
        export_plate_stl(directory / "model.stl", config)
        stl_info = validate_stl(directory / "model.stl")
        if not stl_info["watertight"]:
            warnings.append("Das erzeugte Platten-STL ist nicht wasserdicht.")

    store.set_progress(job_id, 0.9, "validation", "STEP-Datei wird erneut geprueft.")
    report = build_report(job_id, config, toolpath, metrics, step_path)
    warnings.extend(report.warnings)

    write_project_file(directory / "project.json", config)
    (directory / "report.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    store.update(
        job_id,
        status=JobStatus.completed,
        progress=1.0,
        stage="completed",
        message="Fertig. Alle Dateien stehen zum Download bereit.",
        metrics=metrics,
        artifacts=store.refresh_artifacts(job_id),
        warnings=_unique(warnings),
        report_passed=report.passed,
        error=None,
    )


def _run_relief(store: JobStore, job_id: str, config: ProjectConfig, raster, warnings: list[str]) -> None:
    """Phase-2-Zweig: Hoehenrelief statt Fraesbahn."""
    directory = store.job_dir(job_id)

    store.set_progress(job_id, 0.45, "relief", "Hoehenkarte wird berechnet.")
    surface = build_relief_surface(raster, config)

    if abs(surface.effective_sample_distance_mm - config.relief.sample_distance_mm) > 1e-6:
        warnings.append(
            f"Der Abtastabstand wurde von {config.relief.sample_distance_mm:g} mm auf "
            f"{surface.effective_sample_distance_mm:g} mm vergroebert, damit die STL-Datei "
            "handhabbar bleibt."
        )

    store.set_progress(job_id, 0.6, "preview", "Reliefvorschau wird gezeichnet.")
    if config.output.preview_png:
        render_relief_preview(directory / "toolpath.png", surface.heights_mm, config.relief.height_mm)

    store.set_progress(job_id, 0.75, "stl", "Relief-STL wird erzeugt.")
    export_relief_stl(directory / "model.stl", surface)

    store.set_progress(job_id, 0.9, "validation", "STL wird erneut eingelesen und geprueft.")
    info = validate_stl(directory / "model.stl")

    report = ValidationReport(job_id=job_id, mode="relief")
    report.warnings.extend(warnings)
    report.add(
        "stl_lesbar", info["triangle_count"] > 0, f"{info['triangle_count']} Dreiecke gelesen.",
        value=info["triangle_count"],
    )
    report.add("stl_wasserdicht", bool(info["watertight"]), "Jede Kante gehoert genau zwei Dreiecken.")
    report.add(
        "stl_orientierung",
        bool(info["consistently_oriented"]),
        "Alle Dreiecksnormalen zeigen nach aussen.",
    )
    size = info["size_mm"]
    report.add(
        "relief_abmessungen",
        abs(size[0] - config.plate.width_mm) < 0.01 and abs(size[1] - config.plate.height_mm) < 0.01,
        f"Gemessen {size[0]} x {size[1]} x {size[2]} mm.",
        value=size,
        expected=f"{config.plate.width_mm} x {config.plate.height_mm} mm",
    )
    max_total = config.relief.height_mm + config.relief.base_thickness_mm
    report.add(
        "relief_staerke",
        size[2] <= config.plate.thickness_mm + 0.01,
        f"Gesamtstaerke {size[2]} mm bei zulaessigen {config.plate.thickness_mm} mm.",
        value=size[2],
        expected=f"hoechstens {max_total} mm",
    )
    report.finalize()

    write_project_file(directory / "project.json", config)
    (directory / "report.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    store.update(
        job_id,
        status=JobStatus.completed,
        progress=1.0,
        stage="completed",
        message="Relief fertig. Das STL steht zum Download bereit.",
        artifacts=store.refresh_artifacts(job_id),
        warnings=_unique(warnings),
        report_passed=report.passed,
        error=None,
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
