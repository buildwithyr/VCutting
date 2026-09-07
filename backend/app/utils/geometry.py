"""Reine Geometriehilfen ohne Abhaengigkeit zu Bildverarbeitung oder OCC."""

from __future__ import annotations

import math

import numpy as np


def groove_width_mm(depth_mm: float, angle_deg: float) -> float:
    """Nutbreite eines V-Fraesers an der Oberflaeche.

    Nutbreite = 2 * Tiefe * tan(Winkel / 2)
    """
    if depth_mm < 0:
        raise ValueError("depth_mm darf nicht negativ sein.")
    if not 0.0 < angle_deg < 180.0:
        raise ValueError("angle_deg muss zwischen 0 und 180 Grad liegen.")
    return 2.0 * depth_mm * math.tan(math.radians(angle_deg) / 2.0)


def depth_for_groove_width_mm(width_mm: float, angle_deg: float) -> float:
    """Umkehrung von :func:`groove_width_mm`."""
    if width_mm < 0:
        raise ValueError("width_mm darf nicht negativ sein.")
    if not 0.0 < angle_deg < 180.0:
        raise ValueError("angle_deg muss zwischen 0 und 180 Grad liegen.")
    return width_mm / (2.0 * math.tan(math.radians(angle_deg) / 2.0))


def remaining_thickness_mm(thickness_mm: float, max_depth_mm: float) -> float:
    """Verbleibende Materialstaerke unter der tiefsten Nut."""
    return thickness_mm - max_depth_mm


def rdp_mask(points: np.ndarray, epsilon: float) -> np.ndarray:
    """Ramer-Douglas-Peucker als Boolean-Maske der zu behaltenden Punkte.

    Iterativ implementiert, damit auch sehr lange Profile keine
    Rekursionsgrenze reissen. Der Abstand wird zum *Segment* gemessen, nicht
    zur unendlichen Geraden - das ist bei stark gestauchten Profilen stabiler.
    """
    points = np.asarray(points, dtype=float)
    n = len(points)
    if n <= 2:
        return np.ones(n, dtype=bool)
    if epsilon <= 0:
        return np.ones(n, dtype=bool)

    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[-1] = True

    stack: list[tuple[int, int]] = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        p0 = points[i]
        seg = points[j] - p0
        inner = points[i + 1 : j]
        length_sq = float(seg @ seg)
        if length_sq == 0.0:
            dist = np.linalg.norm(inner - p0, axis=1)
        else:
            t = np.clip(((inner - p0) @ seg) / length_sq, 0.0, 1.0)
            proj = p0 + t[:, None] * seg
            dist = np.linalg.norm(inner - proj, axis=1)
        k = int(np.argmax(dist))
        if dist[k] > epsilon:
            split = i + 1 + k
            keep[split] = True
            stack.append((i, split))
            stack.append((split, j))
    return keep


def rdp(points: np.ndarray, epsilon: float) -> np.ndarray:
    """Vereinfachte Punktfolge nach Ramer-Douglas-Peucker."""
    points = np.asarray(points, dtype=float)
    return points[rdp_mask(points, epsilon)]


def polyline_length(points: np.ndarray) -> float:
    """Gesamtlaenge eines Polygonzugs beliebiger Dimension."""
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def dedupe_consecutive(points: np.ndarray, tol: float = 1e-9) -> np.ndarray:
    """Entfernt aufeinanderfolgende identische Punkte.

    OCC erzeugt aus Nulllaengen-Segmenten ungueltige Kanten, deshalb muss das
    vor jeder Kurvenerzeugung passieren.
    """
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        return points
    diff = np.linalg.norm(np.diff(points, axis=0), axis=1)
    keep = np.concatenate(([True], diff > tol))
    return points[keep]
