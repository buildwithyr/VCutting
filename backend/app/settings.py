"""Laufzeiteinstellungen des Backends."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("VCUTTING_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
JOBS_DIR = DATA_DIR / "jobs"

WORKING_PIXELS_PER_MM = float(os.environ.get("VCUTTING_PX_PER_MM", "4.0"))
"""Aufloesung des internen Arbeitsrasters in Pixel je Millimeter.

4 px/mm sind bei 2 mm Linienabstand acht Rasterpunkte je Abtastschritt und
damit fein genug, ohne den Speicher zu sprengen (400 mm -> 1600 px).
"""

MAX_WORKING_PIXELS = 30_000_000
"""Obergrenze des Arbeitsrasters. Grosse Platten reduzieren die Aufloesung."""

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "VCUTTING_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
    ).split(",")
    if origin.strip()
]

JOB_RETENTION_SECONDS = int(os.environ.get("VCUTTING_JOB_RETENTION_SECONDS", str(24 * 3600)))
"""Nach dieser Zeit darf ein Jobverzeichnis automatisch geloescht werden."""


def working_pixels_per_mm(width_mm: float, height_mm: float) -> float:
    """Aufloesung, die sowohl fein genug als auch speichervertraeglich ist."""
    px_per_mm = WORKING_PIXELS_PER_MM
    while px_per_mm > 0.5 and (width_mm * px_per_mm) * (height_mm * px_per_mm) > MAX_WORKING_PIXELS:
        px_per_mm /= 2.0
    return px_per_mm


def ensure_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
