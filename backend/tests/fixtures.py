"""Programmatisch erzeugte Testbilder.

Es werden bewusst keine fremden Beispielbilder eingecheckt. Alle Testdaten
entstehen hier zur Laufzeit.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image


def asymmetric_motif_rgba(width: int = 320, height: int = 240) -> np.ndarray:
    """Transparentes Testmotiv mit eindeutiger Orientierung.

    Aufbau:

    * gefuellte Ellipse als Hauptmotiv,
    * ein *schwarzes* Quadrat oben links innerhalb der Ellipse,
    * ein *helles* Quadrat unten rechts,
    * horizontaler Helligkeitsverlauf.

    Dadurch laesst sich jede Spiegelung und jede Drehung eindeutig erkennen.
    """
    rgba = np.zeros((height, width, 4), dtype=np.uint8)

    yy, xx = np.mgrid[0:height, 0:width]
    cx, cy = width / 2.0, height / 2.0
    rx, ry = width * 0.38, height * 0.38
    ellipse = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0

    gradient = np.linspace(220, 90, width, dtype=np.float32)[None, :].repeat(height, axis=0)
    grey = gradient.astype(np.uint8)

    rgba[..., 0] = grey
    rgba[..., 1] = grey
    rgba[..., 2] = grey
    rgba[..., 3] = np.where(ellipse, 255, 0).astype(np.uint8)

    # Dunkles Quadrat oben links (kleine Zeilen-/Spaltenindizes).
    ty0, ty1 = int(height * 0.22), int(height * 0.36)
    tx0, tx1 = int(width * 0.26), int(width * 0.40)
    dark = ellipse.copy()
    dark[:] = False
    dark[ty0:ty1, tx0:tx1] = True
    dark &= ellipse
    rgba[dark, 0:3] = 8
    rgba[dark, 3] = 255

    # Helles Quadrat unten rechts.
    by0, by1 = int(height * 0.64), int(height * 0.78)
    bx0, bx1 = int(width * 0.60), int(width * 0.74)
    bright = np.zeros_like(ellipse)
    bright[by0:by1, bx0:bx1] = True
    bright &= ellipse
    rgba[bright, 0:3] = 252
    rgba[bright, 3] = 255

    return rgba


def add_speckles(rgba: np.ndarray, count: int = 12, seed: int = 7) -> np.ndarray:
    """Streut isolierte Einzelpixel ausserhalb des Motivs ein."""
    rng = np.random.default_rng(seed)
    out = rgba.copy()
    height, width = out.shape[:2]
    for _ in range(count):
        y = int(rng.integers(2, height - 2))
        x = int(rng.integers(2, width - 2))
        if out[y, x, 3] > 0:
            continue
        out[y, x, 0:3] = 20
        out[y, x, 3] = 255
    return out


def to_png_bytes(rgba: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def opaque_motif_png_bytes(width: int = 240, height: int = 180) -> bytes:
    """Motiv auf weissem Grund, also ohne Alphakanal."""
    rgba = asymmetric_motif_rgba(width, height)
    rgb = np.full((height, width, 3), 255, dtype=np.uint8)
    solid = rgba[..., 3] > 0
    rgb[solid] = rgba[solid, 0:3]
    buffer = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def transparent_motif_png_bytes(width: int = 320, height: int = 240, speckles: bool = True) -> bytes:
    rgba = asymmetric_motif_rgba(width, height)
    if speckles:
        rgba = add_speckles(rgba)
    return to_png_bytes(rgba)


def corrupt_png_bytes() -> bytes:
    """Gueltiger PNG-Header, danach Muell."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
