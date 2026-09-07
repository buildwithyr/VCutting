"""Schritt 3: Motivkontur und Motivhuelle.

Die Bahn darf nicht ueber das rechteckige Bild oder die ganze Platte laufen.
Sie folgt der Motivmaske, erweitert um den eingestellten Motivrand.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.services.tone_mapping import PlateRaster


@dataclass
class MotifEnvelope:
    """Erweiterte Motivmaske samt Konturen fuer die Vorschau."""

    mask: np.ndarray
    """HxW bool, Motivmaske plus Rand."""

    margin_mm: float
    motif_contours_mm: list[np.ndarray]
    """Aussenkonturen des Motivs als Nx2 Arrays in mm."""

    envelope_contours_mm: list[np.ndarray]
    """Aussenkonturen der erweiterten Maske als Nx2 Arrays in mm."""


def dilate_mask_mm(mask: np.ndarray, margin_mm: float, px_per_mm: float) -> np.ndarray:
    """Euklidische Dilatation der Maske um margin_mm.

    Statt eines morphologischen Kernels wird die Distanztransformation
    verwendet. Das ergibt einen geometrisch sauberen Abstand in alle
    Richtungen, unabhaengig von der Kernelform.
    """
    if margin_mm <= 0:
        return mask.copy()
    if not mask.any():
        return mask.copy()

    radius_px = margin_mm * px_per_mm
    outside = (~mask).astype(np.uint8)
    # DIST_L2 mit Maske 5 liefert eine gute Naeherung des echten Abstands.
    distance = cv2.distanceTransform(outside, cv2.DIST_L2, 5)
    return mask | (distance <= radius_px)


def _contours_mm(mask: np.ndarray, raster: PlateRaster) -> list[np.ndarray]:
    """Aussenkonturen einer Maske in Millimeterkoordinaten."""
    if not mask.any():
        return []
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result: list[np.ndarray] = []
    for contour in contours:
        pts = contour.reshape(-1, 2).astype(float)
        if len(pts) < 2:
            continue
        xs = raster.col_to_x(pts[:, 0])
        ys = raster.row_to_y(pts[:, 1])
        result.append(np.column_stack([xs, ys]))
    return result


def build_envelope(raster: PlateRaster, margin_mm: float) -> MotifEnvelope:
    """Erzeugt die Motivhuelle und die Konturen fuer die Vorschau."""
    envelope = dilate_mask_mm(raster.mask, margin_mm, raster.px_per_mm)
    return MotifEnvelope(
        mask=envelope,
        margin_mm=margin_mm,
        motif_contours_mm=_contours_mm(raster.mask, raster),
        envelope_contours_mm=_contours_mm(envelope, raster),
    )
