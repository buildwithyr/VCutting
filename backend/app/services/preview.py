"""Serverseitige Pruefvorschauen.

Matplotlib wird ausschliesslich hier verwendet und laeuft ohne Fenstersystem.
Farbgebung laut Spezifikation:

* Rot  - Fraesbewegungen
* Blau - Leerbewegungen auf Sicherheits-Z
* Gruen - Motivkontur samt Rand
* Schwarz - Plattenumriss
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from PIL import Image  # noqa: E402

from app.models.config import ProjectConfig  # noqa: E402
from app.services.motif_envelope import MotifEnvelope  # noqa: E402
from app.services.raster_paths import Toolpath  # noqa: E402
from app.services.tone_mapping import PlateRaster  # noqa: E402

COLOR_CUT = "#d62728"
COLOR_TRAVEL = "#1f77b4"
COLOR_MOTIF = "#2ca02c"
COLOR_ENVELOPE = "#2ca02c"
COLOR_PLATE = "#000000"

PREVIEW_DPI = 110
MAX_PREVIEW_INCHES = 11.0


def _figure_size(config: ProjectConfig) -> tuple[float, float]:
    width_mm = config.plate.width_mm
    height_mm = config.plate.height_mm
    scale = MAX_PREVIEW_INCHES / max(width_mm, height_mm)
    return max(3.0, width_mm * scale), max(3.0, height_mm * scale)


def _segments_by_kind(toolpath: Toolpath) -> tuple[list, list]:
    """Zerlegt die Bahn in Fraes- und Leerbewegungen."""
    cut_segments: list = []
    travel_segments: list = []
    for kind, points in toolpath.ordered_segments():
        if len(points) < 2:
            continue
        starts, ends = points[:-1], points[1:]
        for start, end in zip(starts, ends, strict=True):
            segment = [(start[0], start[1]), (end[0], end[1])]
            is_cut = kind == "line" and min(start[2], end[2]) < 0.0
            (cut_segments if is_cut else travel_segments).append(segment)
    return cut_segments, travel_segments


def render_toolpath_preview(
    path: Path,
    config: ProjectConfig,
    raster: PlateRaster,
    envelope: MotifEnvelope,
    toolpath: Toolpath,
) -> None:
    """Zeichnet Platte, Motivkontur, Motivhuelle und die berechnete Bahn."""
    width_in, height_in = _figure_size(config)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=PREVIEW_DPI)

    plate = config.plate
    ax.add_patch(
        plt.Rectangle(
            (0, 0), plate.width_mm, plate.height_mm, fill=False, edgecolor=COLOR_PLATE, linewidth=1.6
        )
    )

    for contour in envelope.motif_contours_mm:
        closed = np.vstack([contour, contour[:1]])
        ax.plot(closed[:, 0], closed[:, 1], color=COLOR_MOTIF, linewidth=1.1)
    for contour in envelope.envelope_contours_mm:
        closed = np.vstack([contour, contour[:1]])
        ax.plot(closed[:, 0], closed[:, 1], color=COLOR_ENVELOPE, linewidth=0.9, linestyle="--", alpha=0.8)

    cut_segments, travel_segments = _segments_by_kind(toolpath)
    if travel_segments:
        ax.add_collection(
            LineCollection(travel_segments, colors=COLOR_TRAVEL, linewidths=0.5, alpha=0.75)
        )
    if cut_segments:
        ax.add_collection(LineCollection(cut_segments, colors=COLOR_CUT, linewidths=0.7))

    ax.set_xlim(-plate.width_mm * 0.03, plate.width_mm * 1.03)
    ax.set_ylim(-plate.height_mm * 0.03, plate.height_mm * 1.03)
    ax.set_aspect("equal")
    ax.set_xlabel("X in mm")
    ax.set_ylabel("Y in mm")
    ax.set_title(
        f"{config.project.name} - {len(toolpath.lines)} Linien, "
        f"Rand {config.carving.motif_margin_mm:g} mm, Sicherheits-Z {config.carving.clearance_z_mm:g} mm"
    )
    ax.grid(True, linewidth=0.3, alpha=0.3)

    fig.tight_layout()
    fig.savefig(path, format="png")
    plt.close(fig)


def render_simulation_preview(
    path: Path, config: ProjectConfig, raster: PlateRaster, toolpath: Toolpath
) -> None:
    """Simuliertes Schwarz-Weiss-Fraesbild aus den tatsaechlichen Bahnpunkten.

    Jede Bahnlinie wird mit der real erzeugten Nutbreite in ein Graustufenbild
    gezeichnet. Dunkel bedeutet tief. So wird sichtbar, was der eingestellte
    Linienabstand tatsaechlich vom Motiv uebrig laesst.
    """
    import cv2

    px_per_mm = min(raster.px_per_mm, 3.0)
    width = max(1, int(round(config.plate.width_mm * px_per_mm)))
    height = max(1, int(round(config.plate.height_mm * px_per_mm)))
    canvas = np.full((height, width), 255, dtype=np.uint8)

    max_depth = config.carving.max_depth_mm
    angle_factor = 2.0 * np.tan(np.radians(config.tool.angle_deg) / 2.0)

    def to_px(point) -> tuple[int, int]:
        return (
            int(round(point[0] * px_per_mm)),
            int(round((config.plate.height_mm - point[1]) * px_per_mm)),
        )

    for line in toolpath.lines:
        points = line.points
        for start, end in zip(points[:-1], points[1:], strict=True):
            depth = -min(start[2], end[2])
            if depth <= 0:
                continue
            groove_px = max(1, int(round(depth * angle_factor * px_per_mm)))
            shade = int(np.clip(255 * (1.0 - depth / max_depth), 0, 255))
            p0, p1 = to_px(start), to_px(end)
            cv2.line(canvas, p0, p1, color=shade, thickness=groove_px, lineType=cv2.LINE_AA)

    Image.fromarray(canvas, mode="L").save(path, format="PNG")


def render_relief_preview(path: Path, heightmap: np.ndarray, height_mm: float) -> None:
    """Graustufenvorschau eines Reliefs. Hell bedeutet hoch."""
    if height_mm <= 0:
        normalized = np.zeros_like(heightmap)
    else:
        normalized = np.clip(heightmap / height_mm, 0.0, 1.0)
    image = (normalized * 255).astype(np.uint8)
    Image.fromarray(image, mode="L").save(path, format="PNG")
