"""Rueckpruefung der erzeugten STEP-Datei.

Die Datei wird nach dem Schreiben erneut eingelesen und gegen die Konfiguration
und die berechnete Bahn geprueft. Alles Wesentliche landet im Bericht, damit
Fehler nachvollziehbar bleiben.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from OCP.BRepCheck import BRepCheck_Analyzer

from app.models.config import MIN_ACCEPTABLE_REDUCTION_PERCENT, ProjectConfig
from app.models.job import PathMetrics
from app.models.report import ValidationReport
from app.services.raster_paths import Toolpath
from app.services.step_export import (
    analyse_free_edges,
    collect_free_edges,
    collect_solids,
    read_step,
)
from app.utils.occ import bbox_of

DIMENSION_TOLERANCE_MM = 1e-3
Z_TOLERANCE_MM = 1e-3

MAX_CONNECTOR_RATIO = 0.25
"""Eine Verbindung darf hoechstens ein Viertel der Motivausdehnung lang sein.

Alles darueber waere eine lange diagonale Rueckfahrt statt eines kurzen
Sprungs zwischen benachbarten Linien.
"""


def _travel_extent_mm(toolpath: Toolpath) -> float:
    """Ausdehnung des Motivs entlang der Verfahrachse."""
    points = toolpath.polyline()
    if len(points) == 0:
        return 0.0
    axis = 1 if toolpath.orientation == "vertical" else 0
    return float(points[:, axis].max() - points[:, axis].min())


def validate_toolpath(report: ValidationReport, config: ProjectConfig, toolpath: Toolpath) -> None:
    """Prueft die Bahn selbst, unabhaengig vom STEP-Export."""
    carving = config.carving
    clearance = carving.clearance_z_mm

    report.add(
        "bahn_vorhanden",
        len(toolpath.lines) > 0,
        f"Die Bahn besteht aus {len(toolpath.lines)} Rasterlinien.",
        value=len(toolpath.lines),
        expected="mindestens 1",
    )

    expected_connectors = max(0, len(toolpath.lines) - 1)
    report.add(
        "verbindungsanzahl",
        len(toolpath.connectors) == expected_connectors,
        f"{len(toolpath.connectors)} Verbindungen bei {len(toolpath.lines)} Linien.",
        value=len(toolpath.connectors),
        expected=f"Linienzahl - 1 = {expected_connectors}",
    )

    endpoints_ok = all(
        abs(line.points[0][2] - clearance) <= Z_TOLERANCE_MM
        and abs(line.points[-1][2] - clearance) <= Z_TOLERANCE_MM
        for line in toolpath.lines
    )
    report.add(
        "linienenden_auf_sicherheits_z",
        endpoints_ok,
        "Jede Rasterlinie beginnt und endet auf der Sicherheitshoehe.",
        expected=f"Z = {clearance} mm",
    )

    connectors_flat = all(
        abs(connector.start[2] - clearance) <= Z_TOLERANCE_MM
        and abs(connector.end[2] - clearance) <= Z_TOLERANCE_MM
        for connector in toolpath.connectors
    )
    report.add(
        "verbindungen_auf_sicherheits_z",
        connectors_flat,
        "Keine Verbindung taucht ins Material ein.",
        expected=f"Z = {clearance} mm",
    )

    same_end = all(
        previous.finish_end == following.start_end
        for previous, following in zip(toolpath.lines, toolpath.lines[1:], strict=False)
    )
    report.add(
        "verbindungen_am_gleichen_ende",
        same_end,
        "Jede Verbindung sitzt am gleichen oberen beziehungsweise unteren Ende.",
    )

    alternating = all(
        line.reversed_direction == (index % 2 == 1) for index, line in enumerate(toolpath.lines)
    )
    report.add(
        "schlangenrichtung_wechselt",
        alternating,
        "Die Verfahrrichtung wechselt von Linie zu Linie.",
    )

    extent = _travel_extent_mm(toolpath)
    longest = max((connector.length_mm for connector in toolpath.connectors), default=0.0)
    limit = max(3 * carving.line_spacing_mm, MAX_CONNECTOR_RATIO * extent)
    report.add(
        "keine_langen_rueckfahrten",
        longest <= limit,
        f"Laengste Verbindung {longest:.2f} mm bei einer Motivausdehnung von {extent:.1f} mm.",
        value=round(longest, 3),
        expected=f"hoechstens {limit:.2f} mm",
    )

    points = toolpath.polyline()
    z_min = float(points[:, 2].min()) if len(points) else 0.0
    z_max = float(points[:, 2].max()) if len(points) else 0.0

    report.add(
        "maximale_tiefe_eingehalten",
        z_min >= -carving.max_depth_mm - Z_TOLERANCE_MM,
        f"Tiefster Bahnpunkt bei Z = {z_min:.4f} mm.",
        value=round(z_min, 4),
        expected=f"nicht tiefer als {-carving.max_depth_mm} mm",
    )
    report.add(
        "sicherheitshoehe_ist_z_maximum",
        abs(z_max - clearance) <= Z_TOLERANCE_MM,
        f"Hoechster Bahnpunkt bei Z = {z_max:.4f} mm.",
        value=round(z_max, 4),
        expected=f"Z = {clearance} mm",
    )
    report.add(
        "reststaerke_positiv",
        config.remaining_thickness_mm > 0,
        f"Unter der tiefsten Nut bleiben {config.remaining_thickness_mm:.2f} mm Material.",
        value=round(config.remaining_thickness_mm, 4),
        expected="groesser als 0 mm",
    )

    plate = config.plate
    if len(points):
        inside = (
            points[:, 0].min() >= -DIMENSION_TOLERANCE_MM
            and points[:, 1].min() >= -DIMENSION_TOLERANCE_MM
            and points[:, 0].max() <= plate.width_mm + DIMENSION_TOLERANCE_MM
            and points[:, 1].max() <= plate.height_mm + DIMENSION_TOLERANCE_MM
        )
    else:
        inside = False
    report.add(
        "bahn_innerhalb_der_platte",
        inside,
        "Die gesamte Bahn liegt innerhalb der Plattenabmessungen.",
        value=[round(float(v), 3) for v in points[:, :2].min(axis=0)] if len(points) else None,
    )


def validate_metrics(report: ValidationReport, config: ProjectConfig, metrics: PathMetrics) -> None:
    """Prueft die Vereinfachungskennzahlen."""
    target = config.simplification.target_reduction
    reached = metrics.reduction_percent

    report.add(
        "punktreduktion",
        reached >= MIN_ACCEPTABLE_REDUCTION_PERCENT,
        (
            f"Reduktion {reached:.2f} Prozent "
            f"({metrics.raw_point_count} -> {metrics.simplified_point_count} Punkte)."
        ),
        value=reached,
        expected=f"mindestens {MIN_ACCEPTABLE_REDUCTION_PERCENT} Prozent",
    )
    if reached < target:
        report.warnings.append(
            f"Die Vereinfachungsstufe '{config.simplification.mode}' zielt auf {target:.0f} Prozent "
            f"Reduktion, erreicht wurden {reached:.2f} Prozent."
        )
    if reached < MIN_ACCEPTABLE_REDUCTION_PERCENT:
        report.warnings.append(
            "Weniger als 85 Prozent Reduktion. Eine staerkere Vereinfachungsstufe oder ein "
            "groesserer Linienabstand entlasten CATIA deutlich."
        )


def validate_step_file(
    report: ValidationReport, path: Path, config: ProjectConfig, toolpath: Toolpath
) -> None:
    """Liest die STEP-Datei erneut ein und prueft ihren Inhalt."""
    try:
        shape = read_step(path)
    except Exception as exc:  # noqa: BLE001 - Ursache gehoert in den Bericht
        report.add("step_lesbar", False, f"Die STEP-Datei konnte nicht gelesen werden: {exc}")
        return

    report.add("step_lesbar", True, "Die STEP-Datei laesst sich wieder oeffnen.")

    solids = collect_solids(shape)
    expected_solids = 1 if config.output.include_reference_plate else 0
    report.add(
        "referenzplatte_vorhanden",
        len(solids) == expected_solids,
        f"{len(solids)} Solid(s) in der Datei.",
        value=len(solids),
        expected=str(expected_solids),
    )

    if solids:
        solid = solids[0]
        valid = BRepCheck_Analyzer(solid).IsValid()
        report.add("referenzplatte_gueltig", bool(valid), "Die Referenzplatte ist ein gueltiger Solid.")

        x0, y0, z0, x1, y1, z1 = bbox_of(solid)
        plate = config.plate
        dimensions_ok = (
            abs((x1 - x0) - plate.width_mm) <= DIMENSION_TOLERANCE_MM
            and abs((y1 - y0) - plate.height_mm) <= DIMENSION_TOLERANCE_MM
            and abs((z1 - z0) - plate.thickness_mm) <= DIMENSION_TOLERANCE_MM
            and abs(z1 - plate.top_z_mm) <= DIMENSION_TOLERANCE_MM
        )
        report.add(
            "plattenabmessungen",
            dimensions_ok,
            (
                f"Gemessen {x1 - x0:.3f} x {y1 - y0:.3f} x {z1 - z0:.3f} mm, "
                f"Oberseite bei Z = {z1:.3f} mm."
            ),
            value=[round(x1 - x0, 3), round(y1 - y0, 3), round(z1 - z0, 3)],
            expected=f"{plate.width_mm} x {plate.height_mm} x {plate.thickness_mm} mm",
        )

    edges = collect_free_edges(shape)
    analysis = analyse_free_edges(edges, toolpath.orientation)

    expected_edges = len(toolpath.lines) + len(toolpath.connectors)
    report.add(
        "bahn_in_step_vorhanden",
        analysis["edge_count"] > 0,
        f"{analysis['edge_count']} freie Kanten bilden die Fraesbahn.",
        value=analysis["edge_count"],
        expected=str(expected_edges),
    )
    report.add(
        "bahn_zusammenhaengend",
        bool(analysis["connected"]) and analysis["branch_nodes"] == 0,
        (
            f"Zusammenhang: {analysis['connected']}, offene Enden: {analysis['open_ends']}, "
            f"Verzweigungen: {analysis['branch_nodes']}."
        ),
        expected="ein durchgehender Zug mit genau 2 offenen Enden",
    )
    report.add(
        "anzahl_rasterlinien",
        analysis["line_edges"] == len(toolpath.lines),
        f"{analysis['line_edges']} Rasterlinien in der STEP-Datei.",
        value=analysis["line_edges"],
        expected=str(len(toolpath.lines)),
    )
    report.add(
        "anzahl_verbindungen",
        analysis["connector_edges"] == len(toolpath.connectors),
        f"{analysis['connector_edges']} Verbindungen in der STEP-Datei.",
        value=analysis["connector_edges"],
        expected=str(len(toolpath.connectors)),
    )

    if edges:
        boxes = np.array([bbox_of(edge) for edge in edges])
        step_min = boxes[:, :3].min(axis=0)
        step_max = boxes[:, 3:].max(axis=0)
        expected_points = toolpath.polyline()

        report.add(
            "step_z_maximum",
            abs(step_max[2] - config.carving.clearance_z_mm) <= 1e-2,
            f"Z-Maximum der Bahn in der Datei: {step_max[2]:.4f} mm.",
            value=round(float(step_max[2]), 4),
            expected=f"{config.carving.clearance_z_mm} mm",
        )
        report.add(
            "step_z_minimum",
            step_min[2] >= -config.carving.max_depth_mm - 1e-2,
            f"Z-Minimum der Bahn in der Datei: {step_min[2]:.4f} mm.",
            value=round(float(step_min[2]), 4),
            expected=f"nicht tiefer als {-config.carving.max_depth_mm} mm",
        )

        # Eine Spiegelung wuerde die Huelle der Bahn verschieben.
        expected_min = expected_points.min(axis=0)
        expected_max = expected_points.max(axis=0)
        no_mirror = bool(
            np.allclose(step_min, expected_min, atol=1e-2)
            and np.allclose(step_max, expected_max, atol=1e-2)
        )
        report.add(
            "keine_spiegelung",
            no_mirror,
            "Die Bahnhuelle in der Datei deckt sich mit der berechneten Bahn.",
            value=[round(float(v), 3) for v in step_min],
            expected=str([round(float(v), 3) for v in expected_min]),
        )

    report.add(
        "keine_leeren_koerper",
        not shape.IsNull() and (bool(solids) or analysis["edge_count"] > 0),
        "Die Datei enthaelt keinen leeren geometrischen Satz.",
    )


def build_report(
    job_id: str,
    config: ProjectConfig,
    toolpath: Toolpath,
    metrics: PathMetrics,
    step_path: Path | None,
) -> ValidationReport:
    """Erzeugt den vollstaendigen Pruefbericht."""
    report = ValidationReport(job_id=job_id, mode=config.mode, metrics=metrics)
    report.warnings.extend(config.warnings())

    validate_toolpath(report, config, toolpath)
    validate_metrics(report, config, metrics)
    if step_path is not None:
        validate_step_file(report, step_path, config, toolpath)

    return report.finalize()
