"""Schritt 6: STEP-Erzeugung und Rueckpruefung mit OpenCascade.

Aufbau der Datei:

* ein massiver Referenzquader in exakten Plattenabmessungen,
* ein zusammenhaengender Drahtkoerper der gesamten Fraesbahn,
* beides als Compound gruppiert, aber getrennt auswaehlbar.

Bewusst *nicht* erzeugt wird eine einzige riesige B-Spline ueber die gesamte
Bahn. Aeltere CATIA-STEP-Uebersetzer liefern dabei gelegentlich einen leeren
geometrischen Satz. Stattdessen entsteht je Rasterlinie eine handhabbare
Kurve vom Grad 1 und je Verbindung eine gerade Kante.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.Geom import Geom_BSplineCurve
from OCP.gp import gp_Pnt
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape

from app.models.config import ProjectConfig
from app.services.raster_paths import Toolpath
from app.utils.geometry import dedupe_consecutive
from app.utils.occ import (
    Array1OfInteger,
    Array1OfReal,
    IndexedDataMapOfShapeListOfShape,
    edge_endpoints,
    point_array,
)

VERTEX_TOLERANCE_MM = 1e-4
"""Toleranz, ab der zwei Bahnpunkte als derselbe Punkt gelten."""

MIN_EDGE_LENGTH_MM = 1e-6


class StepExportError(RuntimeError):
    """Die STEP-Datei konnte nicht erzeugt oder nicht geprueft werden."""


def polyline_edge(points: np.ndarray):
    """Eine Kante aus einer B-Spline vom Grad 1 durch alle Punkte.

    Grad 1 bedeutet: die Kurve ist geometrisch exakt ein Polygonzug, wird aber
    als *eine* Entitaet exportiert statt als viele Einzelkanten.
    """
    points = dedupe_consecutive(np.asarray(points, dtype=float), tol=MIN_EDGE_LENGTH_MM)
    count = len(points)
    if count < 2:
        raise StepExportError("Eine Rasterlinie hat weniger als zwei verwertbare Punkte.")

    if count == 2:
        return BRepBuilderAPI_MakeEdge(
            gp_Pnt(*points[0].tolist()), gp_Pnt(*points[1].tolist())
        ).Edge()

    poles = point_array(points)
    knots = Array1OfReal(1, count)
    mults = Array1OfInteger(1, count)
    for index in range(1, count + 1):
        knots.SetValue(index, float(index - 1))
        mults.SetValue(index, 1)
    # Klemmende Randknoten: Summe der Vielfachheiten = Polzahl + Grad + 1.
    mults.SetValue(1, 2)
    mults.SetValue(count, 2)

    curve = Geom_BSplineCurve(poles, knots, mults, 1)
    maker = BRepBuilderAPI_MakeEdge(curve)
    if not maker.IsDone():
        raise StepExportError("OpenCascade konnte aus der Rasterlinie keine Kante erzeugen.")
    return maker.Edge()


def build_plate_solid(config: ProjectConfig):
    """Referenzplatte als geschlossener BRep-Solid.

    Oberseite bei Z = top_z_mm, Unterseite bei top_z_mm - Plattenstaerke.
    """
    plate = config.plate
    origin = gp_Pnt(0.0, 0.0, plate.top_z_mm - plate.thickness_mm)
    maker = BRepPrimAPI_MakeBox(origin, plate.width_mm, plate.height_mm, plate.thickness_mm)
    maker.Build()
    if not maker.IsDone():
        raise StepExportError("Die Referenzplatte konnte nicht erzeugt werden.")
    solid = maker.Shape()
    if not BRepCheck_Analyzer(solid).IsValid():
        raise StepExportError("Die erzeugte Referenzplatte ist kein gueltiger Solid.")
    return solid


def build_toolpath_wire(toolpath: Toolpath):
    """Alle Rasterlinien und Verbindungen als ein zusammenhaengender Wire."""
    if not toolpath.lines:
        raise StepExportError("Die Fraesbahn enthaelt keine Linien.")

    maker = BRepBuilderAPI_MakeWire()
    for index, line in enumerate(toolpath.lines):
        if index > 0:
            connector = toolpath.connectors[index - 1]
            if float(np.linalg.norm(connector.end - connector.start)) > MIN_EDGE_LENGTH_MM:
                maker.Add(
                    BRepBuilderAPI_MakeEdge(
                        gp_Pnt(*connector.start.tolist()), gp_Pnt(*connector.end.tolist())
                    ).Edge()
                )
        maker.Add(polyline_edge(line.points))

    if not maker.IsDone():
        raise StepExportError(
            "Die Fraesbahn konnte nicht zu einem zusammenhaengenden Drahtkoerper verbunden werden."
        )
    return maker.Wire()


def build_compound(config: ProjectConfig, toolpath: Toolpath) -> TopoDS_Compound:
    """Platte und Drahtkoerper gemeinsam, aber getrennt auswaehlbar."""
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    if config.output.include_reference_plate:
        builder.Add(compound, build_plate_solid(config))
    builder.Add(compound, build_toolpath_wire(toolpath))
    return compound


def export_step(path: Path, config: ProjectConfig, toolpath: Toolpath) -> Path:
    """Schreibt die STEP-Datei und gibt den Pfad zurueck."""
    compound = build_compound(config, toolpath)
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise StepExportError(f"STEP konnte nicht geschrieben werden (Status {status}).")
    if not path.exists() or path.stat().st_size == 0:
        raise StepExportError("Die geschriebene STEP-Datei ist leer.")
    return path


# ---------------------------------------------------------------------------
# Rueckpruefung
# ---------------------------------------------------------------------------


def read_step(path: Path) -> TopoDS_Shape:
    """Liest eine STEP-Datei wieder ein."""
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise StepExportError(f"STEP-Datei konnte nicht gelesen werden (Status {status}).")
    if reader.NbRootsForTransfer() < 1:
        raise StepExportError("Die STEP-Datei enthaelt keine uebertragbare Wurzel.")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise StepExportError("Die STEP-Datei liefert eine leere Form.")
    return shape


def collect_solids(shape: TopoDS_Shape) -> list:
    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solids.append(explorer.Current())
        explorer.Next()
    return solids


def collect_free_edges(shape: TopoDS_Shape) -> list:
    """Kanten, die zu keiner Flaeche gehoeren - also die Fraesbahn."""
    mapping = IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, mapping)
    return [
        mapping.FindKey(index)
        for index in range(1, mapping.Extent() + 1)
        if mapping.FindFromIndex(index).Extent() == 0
    ]


def count_vertices(shape: TopoDS_Shape) -> int:
    total = 0
    explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
    while explorer.More():
        total += 1
        explorer.Next()
    return total


def _node_key(point: tuple[float, float, float]) -> tuple[int, int, int]:
    scale = 1.0 / VERTEX_TOLERANCE_MM
    return tuple(int(round(value * scale)) for value in point)  # type: ignore[return-value]


def analyse_free_edges(edges: list, orientation: str) -> dict:
    """Prueft Zusammenhang und klassifiziert die Kanten der Bahn.

    Eine Rasterlinie haelt ihre Positionsachse konstant (X bei vertikaler,
    Y bei horizontaler Richtung). Jede Verbindung veraendert sie. Daran lassen
    sich die beiden Kantenarten nach dem Wiedereinlesen sicher unterscheiden.
    """
    axis = 0 if orientation == "vertical" else 1

    nodes: dict[tuple[int, int, int], list[int]] = {}
    edge_nodes: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    line_edges = 0
    connector_edges = 0

    for index, edge in enumerate(edges):
        start, end = edge_endpoints(edge)
        key_start, key_end = _node_key(start), _node_key(end)
        edge_nodes.append((key_start, key_end))
        nodes.setdefault(key_start, []).append(index)
        nodes.setdefault(key_end, []).append(index)
        if math.isclose(start[axis], end[axis], abs_tol=1e-6):
            line_edges += 1
        else:
            connector_edges += 1

    # Zusammenhang ueber eine Tiefensuche entlang gemeinsamer Endpunkte.
    visited: set[int] = set()
    if edges:
        stack = [0]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for node in edge_nodes[current]:
                stack.extend(neighbour for neighbour in nodes[node] if neighbour not in visited)

    degrees = [len(indices) for indices in nodes.values()]
    return {
        "edge_count": len(edges),
        "connected": len(visited) == len(edges),
        "open_ends": sum(1 for degree in degrees if degree == 1),
        "branch_nodes": sum(1 for degree in degrees if degree > 2),
        "line_edges": line_edges,
        "connector_edges": connector_edges,
    }
