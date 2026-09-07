"""Schritt 2: Motiv auf der Platte platzieren und Helligkeit in Tiefe wandeln.

Koordinatensystem (durchgaengig im gesamten Projekt):

* X0/Y0 liegt in der linken unteren Ecke der Platte.
* X waechst nach rechts, Y waechst nach oben.
* Die Plattenoberseite liegt bei Z = 0, die Unterseite bei Z = -Plattenstaerke.
* Frästiefen sind negativ, Sicherheitsfahrten positiv.

Das Arbeitsraster ist ein Bild in Plattengroesse. Zeile 0 des Rasters ist die
*obere* Plattenkante. Die Umrechnung ``y = height_mm - (row + 0.5) * mm_px``
dreht deshalb die Zeilenrichtung um - das ist keine Spiegelung, sondern der
Wechsel von Bild- zu Werkstueckkoordinaten.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.models.config import ProjectConfig
from app.services.image_cleanup import CleanedMotif, luminance
from app.settings import working_pixels_per_mm


@dataclass
class PlateRaster:
    """Arbeitsraster in Plattengroesse."""

    px_per_mm: float
    plate_width_mm: float
    plate_height_mm: float
    mask: np.ndarray
    """HxW bool, True = Motiv."""

    darkness: np.ndarray
    """HxW float32 im Bereich 0..1, ausserhalb der Maske 0."""

    depth: np.ndarray
    """HxW float32, Frästiefe in mm (<= 0). Ausserhalb der Schnittflaeche 0."""

    cut: np.ndarray
    """HxW bool, True wo tatsaechlich gefräst wird."""

    rgb: np.ndarray
    """HxWx3 uint8, das platzierte Motiv auf weissem Grund (fuer Vorschauen)."""

    motif_bbox_mm: tuple[float, float, float, float]
    """(x_min, y_min, x_max, y_max) des platzierten Motivs in mm."""

    @property
    def mm_per_px(self) -> float:
        return 1.0 / self.px_per_mm

    @property
    def height_px(self) -> int:
        return int(self.mask.shape[0])

    @property
    def width_px(self) -> int:
        return int(self.mask.shape[1])

    def col_to_x(self, col: np.ndarray | float) -> np.ndarray | float:
        return (np.asarray(col, dtype=float) + 0.5) * self.mm_per_px

    def row_to_y(self, row: np.ndarray | float) -> np.ndarray | float:
        return self.plate_height_mm - (np.asarray(row, dtype=float) + 0.5) * self.mm_per_px

    def x_to_col(self, x_mm: float) -> int:
        return int(np.clip(round(x_mm * self.px_per_mm - 0.5), 0, self.width_px - 1))

    def y_to_row(self, y_mm: float) -> int:
        raw = (self.plate_height_mm - y_mm) * self.px_per_mm - 0.5
        return int(np.clip(round(raw), 0, self.height_px - 1))


def place_motif(motif: CleanedMotif, config: ProjectConfig) -> PlateRaster:
    """Skaliert das Motiv in den nutzbaren Plattenbereich und zentriert es.

    Das Seitenverhaeltnis bleibt erhalten. Es wird nicht gespiegelt und nicht
    gedreht.
    """
    plate = config.plate
    px_per_mm = working_pixels_per_mm(plate.width_mm, plate.height_mm)

    grid_w = max(1, int(round(plate.width_mm * px_per_mm)))
    grid_h = max(1, int(round(plate.height_mm * px_per_mm)))

    usable_w_mm = plate.width_mm - 2 * plate.margin_mm
    usable_h_mm = plate.height_mm - 2 * plate.margin_mm
    if usable_w_mm <= 0 or usable_h_mm <= 0:
        raise ValueError("Der Plattenrand laesst keine nutzbare Flaeche uebrig.")

    scale = min(usable_w_mm / motif.width * px_per_mm, usable_h_mm / motif.height * px_per_mm)
    target_w = max(1, int(round(motif.width * scale)))
    target_h = max(1, int(round(motif.height * scale)))

    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized_rgb = cv2.resize(motif.rgb, (target_w, target_h), interpolation=interpolation)
    resized_mask = (
        cv2.resize(motif.mask.astype(np.float32), (target_w, target_h), interpolation=interpolation)
        > 0.5
    )
    if not resized_mask.any():
        # Extrem kleine Motive koennen beim Verkleinern verschwinden.
        resized_mask = (
            cv2.resize(motif.mask.astype(np.uint8), (target_w, target_h), interpolation=cv2.INTER_NEAREST)
            > 0
        )

    off_x = (grid_w - target_w) // 2
    off_y = (grid_h - target_h) // 2

    rgb = np.full((grid_h, grid_w, 3), 255, dtype=np.uint8)
    mask = np.zeros((grid_h, grid_w), dtype=bool)
    rgb[off_y : off_y + target_h, off_x : off_x + target_w] = resized_rgb
    mask[off_y : off_y + target_h, off_x : off_x + target_w] = resized_mask
    rgb[~mask] = 255

    mm_per_px = 1.0 / px_per_mm
    bbox = (
        off_x * mm_per_px,
        plate.height_mm - (off_y + target_h) * mm_per_px,
        (off_x + target_w) * mm_per_px,
        plate.height_mm - off_y * mm_per_px,
    )

    darkness, depth, cut = tone_to_depth(rgb, mask, config)

    return PlateRaster(
        px_per_mm=px_per_mm,
        plate_width_mm=plate.width_mm,
        plate_height_mm=plate.height_mm,
        mask=mask,
        darkness=darkness,
        depth=depth,
        cut=cut,
        rgb=rgb,
        motif_bbox_mm=bbox,
    )


def tone_to_depth(
    rgb: np.ndarray, mask: np.ndarray, config: ProjectConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Wandelt Helligkeit in Frästiefe.

    * Graustufen luminanzbasiert (Rec. 709).
    * Dunkelheit = 1 - Grauwert, ausserhalb der Maske 0.
    * Tonwerte bis einschliesslich der Schwelle bleiben ungeschnitten.
    * Frästiefe = -max_depth * darkness ** gamma, nie tiefer als max_depth.
    """
    carving = config.carving
    darkness = (1.0 - luminance(rgb)).astype(np.float32)
    darkness[~mask] = 0.0
    np.clip(darkness, 0.0, 1.0, out=darkness)

    cut = mask & (darkness > carving.tone_threshold)
    depth = np.zeros_like(darkness)
    depth[cut] = -carving.max_depth_mm * np.power(darkness[cut], carving.depth_gamma)
    np.clip(depth, -carving.max_depth_mm, 0.0, out=depth)
    return darkness, depth, cut
