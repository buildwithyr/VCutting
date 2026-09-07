#!/usr/bin/env python3
"""Erzeugt ein transparentes Testmotiv zum Ausprobieren.

Bewusst programmatisch: es liegen keine fremden Beispielbilder im Repository.

Das Motiv ist eindeutig orientiert und eignet sich damit als Sichtprobe:

* ein *dunkles* Quadrat oben links wird am tiefsten gefräst,
* ein *helles* Quadrat unten rechts bleibt ungeschnitten,
* ein Helligkeitsverlauf von links nach rechts zeigt die Tiefenabstufung.

Steht das Ergebnis auf dem Kopf oder ist es gespiegelt, fällt das sofort auf.

Aufruf:

    python examples/testmotiv_erzeugen.py [ziel.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

BREITE = 640
HOEHE = 480


def testmotiv() -> np.ndarray:
    """Transparentes RGBA-Testmotiv mit eindeutiger Orientierung."""
    rgba = np.zeros((HOEHE, BREITE, 4), dtype=np.uint8)

    zeilen, spalten = np.mgrid[0:HOEHE, 0:BREITE]
    mitte_x, mitte_y = BREITE / 2.0, HOEHE / 2.0
    radius_x, radius_y = BREITE * 0.38, HOEHE * 0.38
    ellipse = ((spalten - mitte_x) / radius_x) ** 2 + ((zeilen - mitte_y) / radius_y) ** 2 <= 1.0

    verlauf = np.linspace(220, 90, BREITE, dtype=np.float32)[None, :].repeat(HOEHE, axis=0)
    grau = verlauf.astype(np.uint8)
    rgba[..., 0] = grau
    rgba[..., 1] = grau
    rgba[..., 2] = grau
    rgba[..., 3] = np.where(ellipse, 255, 0).astype(np.uint8)

    dunkel = np.zeros_like(ellipse)
    dunkel[int(HOEHE * 0.22) : int(HOEHE * 0.36), int(BREITE * 0.26) : int(BREITE * 0.40)] = True
    dunkel &= ellipse
    rgba[dunkel, 0:3] = 8

    hell = np.zeros_like(ellipse)
    hell[int(HOEHE * 0.64) : int(HOEHE * 0.78), int(BREITE * 0.60) : int(BREITE * 0.74)] = True
    hell &= ellipse
    rgba[hell, 0:3] = 252

    return rgba


def main() -> int:
    ziel = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("testmotiv.png")
    Image.fromarray(testmotiv(), mode="RGBA").save(ziel, format="PNG")
    print(f"Testmotiv geschrieben: {ziel.resolve()} ({BREITE}x{HOEHE} Pixel, mit Alphakanal)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
