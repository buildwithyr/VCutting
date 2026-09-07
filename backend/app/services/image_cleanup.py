"""Schritt 1 der Pipeline: Bild einlesen, Motivmaske erzeugen und saeubern.

Die Pipeline ist bewusst deterministisch. Es kommt keine KI-Freistellung zum
Einsatz, damit das Ergebnis reproduzierbar und erklaerbar bleibt.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.models.config import Cleanup

ALPHA_CUTOFF = 24
"""Alphawerte darunter gelten als vollstaendig transparent (rund 9 Prozent)."""


class MotifNotFound(ValueError):
    """Nach der Bereinigung ist kein verwertbares Motiv uebrig."""


@dataclass
class CleanedMotif:
    """Auf das Motiv zugeschnittenes Bild samt Maske."""

    rgb: np.ndarray
    """HxWx3 uint8, Farbwerte innerhalb der Maske."""

    mask: np.ndarray
    """HxW bool, True = Motiv."""

    source_size: tuple[int, int]
    """Originalgroesse (Breite, Hoehe) in Pixeln."""

    crop_box: tuple[int, int, int, int]
    """Zuschnitt im Originalbild als (x0, y0, x1, y1), x1/y1 exklusiv."""

    used_alpha: bool
    """True, wenn der Alphakanal als Ausgangsmaske gedient hat."""

    removed_components: int
    """Anzahl entfernter kleiner Inseln."""

    @property
    def height(self) -> int:
        return int(self.mask.shape[0])

    @property
    def width(self) -> int:
        return int(self.mask.shape[1])

    def to_rgba(self) -> np.ndarray:
        """RGBA-Darstellung mit transparentem Hintergrund."""
        rgba = np.zeros((*self.mask.shape, 4), dtype=np.uint8)
        rgba[..., :3] = self.rgb
        rgba[..., 3] = np.where(self.mask, 255, 0).astype(np.uint8)
        return rgba

    def save_png(self, path: Path) -> None:
        Image.fromarray(self.to_rgba(), mode="RGBA").save(path, format="PNG")


def load_rgba(data: bytes) -> np.ndarray:
    """Laedt einen Upload als HxWx4 uint8 Array."""
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if img.mode == "P" and "transparency" in img.info:
            img = img.convert("RGBA")
        elif img.mode not in {"RGBA", "LA"}:
            img = img.convert("RGB")
        return np.array(img.convert("RGBA"), dtype=np.uint8)


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Relative Luminanz nach Rec. 709 im Bereich 0..1."""
    arr = rgb.astype(np.float32) / 255.0
    return 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]


def initial_mask(rgba: np.ndarray, cfg: Cleanup) -> tuple[np.ndarray, bool]:
    """Ausgangsmaske aus Alphakanal oder Hintergrundhelligkeit."""
    alpha = rgba[..., 3]
    has_alpha = bool((alpha < 255).any())

    if has_alpha and cfg.transparent_background:
        return alpha > ALPHA_CUTOFF, True

    # Ohne Alphakanal nehmen wir einen hellen Hintergrund an. Die Schwelle ist
    # einstellbar, eine aggressive Freistellung findet bewusst nicht statt.
    lum = luminance(rgba[..., :3])
    return lum < cfg.background_threshold, False


def remove_small_components(mask: np.ndarray, cfg: Cleanup) -> tuple[np.ndarray, int]:
    """Entfernt Rauschpixel und behaelt optional nur die groesste Komponente."""
    if not mask.any():
        return mask, 0

    uint_mask = mask.astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(uint_mask, connectivity=8)
    if count <= 1:
        return mask, 0

    areas = stats[1:, cv2.CC_STAT_AREA]
    total_pixels = float(mask.size)
    min_area = max(4.0, cfg.min_component_area_ratio * total_pixels)

    if cfg.keep_largest_component:
        keep_labels = {int(np.argmax(areas)) + 1}
    elif cfg.remove_speckles:
        keep_labels = {int(i) + 1 for i, area in enumerate(areas) if area >= min_area}
    else:
        keep_labels = {int(i) + 1 for i in range(len(areas))}

    if not keep_labels:
        # Alles waere weggefallen: die groesste Komponente bleibt in jedem Fall.
        keep_labels = {int(np.argmax(areas)) + 1}

    cleaned = np.isin(labels, list(keep_labels))
    removed = (count - 1) - len(keep_labels)
    return cleaned, max(0, removed)


def smooth_mask(mask: np.ndarray) -> np.ndarray:
    """Glaettet Rastertreppen ohne Loecher im Motiv zu schliessen.

    Erst eine kleine morphologische Oeffnung/Schliessung gegen Einzelpixel,
    danach eine Weichzeichnung mit anschliessender 0.5-Schwelle. Das rundet
    Treppenstufen ab, ohne die Topologie zu veraendern.
    """
    if not mask.any():
        return mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    work = mask.astype(np.uint8)
    work = cv2.morphologyEx(work, cv2.MORPH_OPEN, kernel)
    work = cv2.morphologyEx(work, cv2.MORPH_CLOSE, kernel)
    blurred = cv2.GaussianBlur(work.astype(np.float32), (0, 0), sigmaX=0.8)
    smoothed = blurred > 0.5
    # Falls die Glaettung alles ausloescht (sehr duenne Motive), lieber das
    # ungeglaettete Ergebnis behalten als gar nichts.
    return smoothed if smoothed.any() else mask.copy()


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Engste Umschliessung der Maske als (x0, y0, x1, y1), Ende exklusiv."""
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        raise MotifNotFound("Die Motivmaske ist leer.")
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def clean_image(data: bytes, cfg: Cleanup) -> CleanedMotif:
    """Vollstaendige Bereinigung eines Uploads.

    Reihenfolge: Ausgangsmaske, kleine Komponenten entfernen, Kontur glaetten,
    auf den Motivinhalt zuschneiden. Es wird weder gespiegelt noch gedreht.
    """
    rgba = load_rgba(data)
    height, width = rgba.shape[:2]

    mask, used_alpha = initial_mask(rgba, cfg)
    if not mask.any():
        raise MotifNotFound(
            "Es wurde kein Motiv gefunden. Bei Bildern ohne Transparenz hilft eine "
            "niedrigere Hintergrundschwelle."
        )

    removed = 0
    if cfg.remove_speckles or cfg.keep_largest_component:
        mask, removed = remove_small_components(mask, cfg)

    if cfg.smooth_raster_edges:
        mask = smooth_mask(mask)

    if not mask.any():
        raise MotifNotFound("Nach der Bereinigung ist kein Motiv mehr uebrig.")

    x0, y0, x1, y1 = bounding_box(mask)
    cropped_mask = mask[y0:y1, x0:x1]
    cropped_rgb = rgba[y0:y1, x0:x1, :3].copy()
    cropped_rgb[~cropped_mask] = 255  # Hintergrund neutral weiss, Tiefe 0

    return CleanedMotif(
        rgb=cropped_rgb,
        mask=cropped_mask,
        source_size=(width, height),
        crop_box=(x0, y0, x1, y1),
        used_alpha=used_alpha,
        removed_components=removed,
    )
