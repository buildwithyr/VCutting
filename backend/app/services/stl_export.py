"""STL-Export.

Zwei Faelle:

* ``v_cutting`` - die Referenzplatte als Quader. Die Fraesbahn selbst ist ein
  Drahtkoerper und laesst sich nicht sinnvoll triangulieren.
* ``relief`` - ein geschlossener Koerper aus einer Hoehenkarte.

Bewusste Begrenzung: ein fein trianguliertes Relief wird *nicht* zusaetzlich
als facettiertes STEP exportiert. Ein Gitter mit einigen hunderttausend
Dreiecken erzeugt dabei sehr grosse Dateien und einen enormen Speicherbedarf
im STEP-Uebersetzer. Fuer Relief gilt daher STL, fuer V-Cutting STEP.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter
from stl import mesh as stl_mesh

from app.models.config import ProjectConfig
from app.services.tone_mapping import PlateRaster

VERTEX_ROUND_DECIMALS = 6

MAX_RELIEF_GRID_POINTS = 150_000
"""Obergrenze des Hoehenrasters, rund 390 x 390 Punkte.

Daraus entstehen etwa 600.000 Dreiecke und eine STL-Datei um die 30 MB. Ein
feiner eingestellter Abtastabstand wird automatisch vergroebert, damit der
Download handhabbar bleibt.
"""


class StlExportError(RuntimeError):
    """Das STL konnte nicht erzeugt oder nicht geprueft werden."""


@dataclass
class ReliefSurface:
    """Hoehenkarte in Millimetern samt Rasterabstaenden."""

    heights_mm: np.ndarray
    """(ny, nx) float, Werte zwischen 0 und height_mm."""

    x_mm: np.ndarray
    y_mm: np.ndarray
    top_z_mm: float
    """Z-Wert bei Hoehe 0 - die tiefste Stelle der Reliefoberflaeche."""

    bottom_z_mm: float
    effective_sample_distance_mm: float
    """Tatsaechlich verwendeter Rasterabstand nach der Gitterbegrenzung."""


def build_relief_surface(raster: PlateRaster, config: ProjectConfig) -> ReliefSurface:
    """Erzeugt die Hoehenkarte aus dem bereinigten Graustufenbild.

    Helle Stellen des Motivs liegen hoch, der Hintergrund liegt auf der
    Grundflaeche. ``invert`` dreht das um. Die Reliefoberflaeche endet
    buendig mit der Plattenoberseite, das Material liegt also darunter.
    """
    relief = config.relief
    sample_mm = relief.sample_distance_mm

    # Gitter begrenzen, sonst wird die STL-Datei unhandlich gross.
    plate_points = (config.plate.width_mm / sample_mm) * (config.plate.height_mm / sample_mm)
    if plate_points > MAX_RELIEF_GRID_POINTS:
        sample_mm *= float(np.sqrt(plate_points / MAX_RELIEF_GRID_POINTS))

    step_px = max(1, int(round(sample_mm * raster.px_per_mm)))

    brightness = (1.0 - raster.darkness).astype(np.float32)
    values = np.where(raster.mask, raster.darkness if relief.invert else brightness, 0.0)
    values = values.astype(np.float32)

    if relief.smoothing_mm > 0:
        sigma = relief.smoothing_mm * raster.px_per_mm / 2.3548200450309493
        if sigma > 0.3:
            values = gaussian_filter(values, sigma=sigma, mode="nearest")

    target_w = max(2, raster.width_px // step_px)
    target_h = max(2, raster.height_px // step_px)
    resampled = cv2.resize(values, (target_w, target_h), interpolation=cv2.INTER_AREA)
    np.clip(resampled, 0.0, 1.0, out=resampled)

    # Bildzeile 0 ist die obere Plattenkante, deshalb wird die Zeilenrichtung
    # beim Uebergang in Werkstueckkoordinaten umgedreht.
    heights = np.flipud(resampled) * relief.height_mm

    x_mm = np.linspace(0.0, config.plate.width_mm, target_w)
    y_mm = np.linspace(0.0, config.plate.height_mm, target_h)

    return ReliefSurface(
        heights_mm=heights.astype(float),
        x_mm=x_mm,
        y_mm=y_mm,
        top_z_mm=config.plate.top_z_mm - relief.height_mm,
        bottom_z_mm=config.plate.top_z_mm - relief.height_mm - relief.base_thickness_mm,
        effective_sample_distance_mm=round(sample_mm, 4),
    )


def _grid_triangles(top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
    """Geschlossenes Dreiecksnetz aus Ober- und Unterflaeche.

    ``top`` und ``bottom`` sind (ny, nx, 3) Punktgitter mit identischen X/Y.
    Erzeugt werden Oberseite, Unterseite und vier Seitenwaende. Jede Kante
    gehoert danach genau zwei Dreiecken - das Netz ist wasserdicht.
    """
    ny, nx = top.shape[:2]
    if ny < 2 or nx < 2:
        raise StlExportError("Das Hoehenraster braucht mindestens 2x2 Punkte.")

    triangles: list[np.ndarray] = []

    a, b = top[:-1, :-1], top[:-1, 1:]
    c, d = top[1:, 1:], top[1:, :-1]
    triangles.append(np.stack([a, b, c], axis=2).reshape(-1, 3, 3))
    triangles.append(np.stack([a, c, d], axis=2).reshape(-1, 3, 3))

    a, b = bottom[:-1, :-1], bottom[:-1, 1:]
    c, d = bottom[1:, 1:], bottom[1:, :-1]
    triangles.append(np.stack([a, c, b], axis=2).reshape(-1, 3, 3))
    triangles.append(np.stack([a, d, c], axis=2).reshape(-1, 3, 3))

    def wall(top_edge: np.ndarray, bottom_edge: np.ndarray, flip: bool) -> None:
        """Eine Seitenwand entlang eines Randes des Gitters.

        ``flip`` dreht die Umlaufrichtung. Zwei gegenueberliegende Waende
        brauchen entgegengesetzte Umlaufrichtungen, damit alle Normalen nach
        aussen zeigen.
        """
        t0, t1 = top_edge[:-1], top_edge[1:]
        b0, b1 = bottom_edge[:-1], bottom_edge[1:]
        first = np.stack([t0, b0, b1], axis=1)
        second = np.stack([t0, b1, t1], axis=1)
        if flip:
            first = first[:, ::-1, :]
            second = second[:, ::-1, :]
        triangles.append(first)
        triangles.append(second)

    wall(top[0, :], bottom[0, :], flip=False)  # y = y_min, Normale -Y
    wall(top[-1, :], bottom[-1, :], flip=True)  # y = y_max, Normale +Y
    wall(top[:, 0], bottom[:, 0], flip=True)  # x = x_min, Normale -X
    wall(top[:, -1], bottom[:, -1], flip=False)  # x = x_max, Normale +X

    return np.concatenate(triangles, axis=0)


def _orient_outward(triangles: np.ndarray) -> np.ndarray:
    """Dreht alle Dreiecke, falls die Normalen nach innen zeigen.

    Das Vorzeichen des eingeschlossenen Volumens verraet die Orientierung.
    Statt jede Wand einzeln von Hand herzuleiten, wird sie hier gemessen.
    """
    v0, v1, v2 = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    signed_volume = float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)
    if signed_volume < 0:
        return triangles[:, ::-1, :]
    return triangles


def _write_stl(path: Path, triangles: np.ndarray) -> None:
    triangles = _orient_outward(np.asarray(triangles, dtype=np.float32))
    data = np.zeros(len(triangles), dtype=stl_mesh.Mesh.dtype)
    data["vectors"] = triangles
    body = stl_mesh.Mesh(data, remove_empty_areas=False)
    body.update_normals()
    body.save(str(path))


def export_relief_stl(path: Path, surface: ReliefSurface) -> Path:
    """Schreibt ein geschlossenes Relief-STL."""
    xx, yy = np.meshgrid(surface.x_mm, surface.y_mm)
    top = np.stack([xx, yy, surface.top_z_mm + surface.heights_mm], axis=-1)
    bottom = np.stack([xx, yy, np.full_like(xx, surface.bottom_z_mm)], axis=-1)
    _write_stl(path, _grid_triangles(top, bottom))
    return path


def export_plate_stl(path: Path, config: ProjectConfig) -> Path:
    """Schreibt die Referenzplatte als STL-Quader."""
    plate = config.plate
    xx, yy = np.meshgrid(np.array([0.0, plate.width_mm]), np.array([0.0, plate.height_mm]))
    top = np.stack([xx, yy, np.full_like(xx, plate.top_z_mm)], axis=-1)
    bottom = np.stack([xx, yy, np.full_like(xx, plate.top_z_mm - plate.thickness_mm)], axis=-1)
    _write_stl(path, _grid_triangles(top, bottom))
    return path


def validate_stl(path: Path) -> dict:
    """Liest das STL erneut ein und prueft Wasserdichtheit und Abmessungen."""
    if not path.exists() or path.stat().st_size == 0:
        raise StlExportError("Die STL-Datei fehlt oder ist leer.")

    body = stl_mesh.Mesh.from_file(str(path))
    vectors = np.asarray(body.vectors, dtype=float)
    if len(vectors) == 0:
        raise StlExportError("Die STL-Datei enthaelt keine Dreiecke.")

    keys = np.round(vectors.reshape(-1, 3), VERTEX_ROUND_DECIMALS)
    unique, indices = np.unique(keys, axis=0, return_inverse=True)
    faces = indices.reshape(-1, 3)

    edge_pairs = np.concatenate(
        [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=0
    )
    undirected = np.sort(edge_pairs, axis=1)
    _, counts = np.unique(undirected, axis=0, return_counts=True)
    watertight = bool((counts == 2).all())

    # Jede gerichtete Kante darf nur einmal vorkommen. Sonst waeren zwei
    # Nachbardreiecke gegenlaeufig orientiert und die Normalen inkonsistent.
    _, directed_counts = np.unique(edge_pairs, axis=0, return_counts=True)
    consistent = bool((directed_counts == 1).all())

    low = vectors.reshape(-1, 3).min(axis=0)
    high = vectors.reshape(-1, 3).max(axis=0)

    v0, v1, v2 = vectors[:, 0], vectors[:, 1], vectors[:, 2]
    volume = float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)

    return {
        "triangle_count": int(len(vectors)),
        "vertex_count": int(len(unique)),
        "watertight": watertight,
        "consistently_oriented": consistent,
        "non_manifold_edges": int((counts != 2).sum()),
        "bbox_min_mm": [round(float(v), 4) for v in low],
        "bbox_max_mm": [round(float(v), 4) for v in high],
        "size_mm": [round(float(v), 4) for v in (high - low)],
        "volume_mm3": round(volume, 3),
    }
