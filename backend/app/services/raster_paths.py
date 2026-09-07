"""Schritt 4: Motivbegrenzte Rasterlinien und Schlangenbahn.

Die Bahn laeuft ausschliesslich innerhalb der Motivhuelle. Je Rasterlinie wird
nur der Abschnitt zwischen dem obersten und dem untersten Punkt der Huelle
erzeugt. Der rechteckige Bildhintergrund wird dadurch nie ueberfahren.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.models.config import ProjectConfig
from app.models.job import PathMetrics
from app.services.motif_envelope import MotifEnvelope
from app.services.simplify_paths import reduction_percent, simplify_profile, smooth_profile
from app.services.tone_mapping import PlateRaster
from app.utils.geometry import polyline_length


class EmptyToolpath(ValueError):
    """Es konnte keine einzige Rasterlinie erzeugt werden."""


@dataclass
class RasterLine:
    """Eine einzelne Fraeslinie in Reihenfolge der Verfahrbewegung."""

    index: int
    position_mm: float
    """Konstante Koordinate: X bei vertikaler, Y bei horizontaler Richtung."""

    reversed_direction: bool
    """False = erste Richtung (oben->unten bzw. links->rechts)."""

    points: np.ndarray
    """Nx3 float (x, y, z) in mm, in Verfahrreihenfolge."""

    raw_point_count: int
    """Punktzahl vor der Vereinfachung (ein Punkt je Rasterpixel)."""

    start_end: str
    """Welches Ende der Reisekoordinate am Anfang steht: 'high' oder 'low'."""

    finish_end: str
    """Welches Ende am Schluss steht."""

    @property
    def point_count(self) -> int:
        return int(len(self.points))


@dataclass
class Connector:
    """Leerfahrt zwischen zwei benachbarten Rasterlinien auf Sicherheits-Z."""

    start: np.ndarray
    end: np.ndarray
    end_side: str
    """'high' oder 'low' - beide Linien muessen am selben Ende verbunden werden."""

    @property
    def length_mm(self) -> float:
        return float(np.linalg.norm(self.end - self.start))


@dataclass
class Toolpath:
    lines: list[RasterLine] = field(default_factory=list)
    connectors: list[Connector] = field(default_factory=list)
    orientation: str = "vertical"
    clearance_z_mm: float = 1.0
    max_depth_mm: float = 1.2
    raw_point_count: int = 0

    def polyline(self) -> np.ndarray:
        """Die vollstaendige Bahn als zusammenhaengender Punktzug."""
        if not self.lines:
            return np.zeros((0, 3), dtype=float)
        # Die Verbindungen teilen sich ihre Endpunkte mit den Linien, deshalb
        # ergibt das Aneinanderhaengen der Linien bereits die gesamte Bahn.
        return np.vstack([line.points for line in self.lines])

    def ordered_segments(self) -> list[tuple[str, np.ndarray]]:
        """Bahn als abwechselnde Folge von Linien und Verbindungen."""
        segments: list[tuple[str, np.ndarray]] = []
        for i, line in enumerate(self.lines):
            segments.append(("line", line.points))
            if i < len(self.connectors):
                connector = self.connectors[i]
                segments.append(("connector", np.vstack([connector.start, connector.end])))
        return segments

    def metrics(self, config: ProjectConfig, raster: PlateRaster) -> PathMetrics:
        simplified = sum(line.point_count for line in self.lines)
        counts = [line.point_count for line in self.lines] or [0]

        cut_length = 0.0
        travel_length = 0.0
        for kind, points in self.ordered_segments():
            if len(points) < 2:
                continue
            starts, ends = points[:-1], points[1:]
            lengths = np.linalg.norm(ends - starts, axis=1)
            cutting = np.minimum(starts[:, 2], ends[:, 2]) < 0.0
            if kind == "connector":
                travel_length += float(lengths.sum())
            else:
                cut_length += float(lengths[cutting].sum())
                travel_length += float(lengths[~cutting].sum())

        all_points = np.vstack([line.points for line in self.lines]) if self.lines else np.zeros((0, 3))
        z_values = all_points[:, 2] if len(all_points) else np.array([0.0])

        # Grobschaetzung: eine STEP-Zeile je Stuetzpunkt plus Verwaltungsdaten.
        estimated_kb = (simplified * 110 + len(self.connectors) * 260 + 40_000) / 1024.0

        return PathMetrics(
            line_count=len(self.lines),
            connector_count=len(self.connectors),
            raw_point_count=self.raw_point_count,
            simplified_point_count=simplified,
            reduction_percent=round(reduction_percent(self.raw_point_count, simplified), 2),
            avg_points_per_line=round(simplified / max(1, len(self.lines)), 2),
            max_points_per_line=int(max(counts)),
            cut_length_mm=round(cut_length, 2),
            travel_length_mm=round(travel_length, 2),
            min_z_mm=round(float(z_values.min()), 4),
            max_z_mm=round(float(z_values.max()), 4),
            longest_connector_mm=round(
                max((c.length_mm for c in self.connectors), default=0.0), 3
            ),
            estimated_step_size_kb=round(estimated_kb, 1),
            groove_width_mm=round(config.groove_width_mm, 4),
            remaining_thickness_mm=round(config.remaining_thickness_mm, 4),
            motif_bbox_mm=[round(v, 3) for v in raster.motif_bbox_mm],
            mm_per_pixel=round(raster.mm_per_px, 5),
        )


def _line_positions(low_mm: float, high_mm: float, spacing_mm: float) -> np.ndarray:
    """Gleichmaessig verteilte Linienpositionen, zentriert im Motivbereich."""
    span = high_mm - low_mm
    if span <= 0:
        return np.array([low_mm])
    count = int(np.floor(span / spacing_mm)) + 1
    used = (count - 1) * spacing_mm
    start = low_mm + (span - used) / 2.0
    return start + np.arange(count) * spacing_mm


def _build_profile(
    darkness_slice: np.ndarray,
    mask_slice: np.ndarray,
    config: ProjectConfig,
    px_per_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Z-Werte und Schnittflags fuer einen Linienabschnitt."""
    carving = config.carving
    smoothing_px = config.simplification.smoothing_distance * px_per_mm
    smoothed = smooth_profile(darkness_slice, smoothing_px)

    # Ausserhalb der Motivmaske wird nie geschnitten. Die Glaettung darf den
    # Schnitt also nicht ueber die Motivkontur hinaustragen.
    cut = mask_slice & (smoothed > carving.tone_threshold)

    z = np.full(smoothed.shape, carving.clearance_z_mm, dtype=float)
    if cut.any():
        depth = -carving.max_depth_mm * np.power(smoothed[cut].astype(float), carving.depth_gamma)
        z[cut] = np.clip(depth, -carving.max_depth_mm, 0.0)

    # Beide Enden jeder Linie liegen auf Sicherheits-Z.
    z[0] = carving.clearance_z_mm
    z[-1] = carving.clearance_z_mm
    cut[0] = False
    cut[-1] = False
    return z, cut


def build_toolpath(raster: PlateRaster, envelope: MotifEnvelope, config: ProjectConfig) -> Toolpath:
    """Erzeugt die vollstaendige Schlangenbahn."""
    if config.carving.orientation == "vertical":
        return _build_vertical(raster, envelope, config)
    return _build_horizontal(raster, envelope, config)


def _finish_toolpath(toolpath: Toolpath) -> Toolpath:
    """Verbindet die Linien in Schlangenreihenfolge auf Sicherheits-Z."""
    if not toolpath.lines:
        raise EmptyToolpath(
            "Innerhalb der Motivhuelle konnte keine Rasterlinie erzeugt werden. "
            "Groesserer Motivrand oder kleinerer Linienabstand hilft."
        )

    for previous, following in zip(toolpath.lines, toolpath.lines[1:], strict=False):
        start = previous.points[-1]
        end = following.points[0]
        if previous.finish_end != following.start_end:
            # Darf strukturell nicht vorkommen; waere eine lange Diagonale.
            raise EmptyToolpath(
                "Schlangenbahn ist inkonsistent: Verbindung wuerde ueber das Motiv laufen."
            )
        toolpath.connectors.append(
            Connector(start=start.copy(), end=end.copy(), end_side=previous.finish_end)
        )
    return toolpath


def _build_vertical(raster: PlateRaster, envelope: MotifEnvelope, config: ProjectConfig) -> Toolpath:
    """Linien mit konstantem X, Verfahren entlang Y."""
    mask = envelope.mask
    cols = np.flatnonzero(mask.any(axis=0))
    if cols.size == 0:
        raise EmptyToolpath("Die Motivhuelle ist leer.")

    x_low = float(raster.col_to_x(cols[0]))
    x_high = float(raster.col_to_x(cols[-1]))
    positions = _line_positions(x_low, x_high, config.carving.line_spacing_mm)

    sample_step = max(1, int(round(config.simplification.sample_distance * raster.px_per_mm)))
    toolpath = Toolpath(
        orientation="vertical",
        clearance_z_mm=config.carving.clearance_z_mm,
        max_depth_mm=config.carving.max_depth_mm,
    )

    for x_mm in positions:
        col = raster.x_to_col(float(x_mm))
        rows = np.flatnonzero(mask[:, col])
        if rows.size < 2:
            continue
        r_top, r_bottom = int(rows[0]), int(rows[-1])

        row_range = np.arange(r_top, r_bottom + 1)
        y_values = np.asarray(raster.row_to_y(row_range), dtype=float)
        z_values, cut_flags = _build_profile(
            raster.darkness[r_top : r_bottom + 1, col],
            raster.mask[r_top : r_bottom + 1, col],
            config,
            raster.px_per_mm,
        )

        profile = simplify_profile(
            y_values, z_values, cut_flags, sample_step, config.simplification.rdp_tolerance
        )
        index = len(toolpath.lines)
        reverse = index % 2 == 1
        if reverse:
            profile = profile[::-1]

        points = np.column_stack(
            [np.full(len(profile), float(x_mm)), profile[:, 0], profile[:, 1]]
        )
        toolpath.lines.append(
            RasterLine(
                index=index,
                position_mm=float(x_mm),
                reversed_direction=reverse,
                points=points,
                raw_point_count=int(row_range.size),
                start_end="low" if reverse else "high",
                finish_end="high" if reverse else "low",
            )
        )
        toolpath.raw_point_count += int(row_range.size)

    return _finish_toolpath(toolpath)


def _build_horizontal(raster: PlateRaster, envelope: MotifEnvelope, config: ProjectConfig) -> Toolpath:
    """Linien mit konstantem Y, Verfahren entlang X."""
    mask = envelope.mask
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        raise EmptyToolpath("Die Motivhuelle ist leer.")

    y_low = float(raster.row_to_y(rows[-1]))
    y_high = float(raster.row_to_y(rows[0]))
    positions = _line_positions(y_low, y_high, config.carving.line_spacing_mm)[::-1]

    sample_step = max(1, int(round(config.simplification.sample_distance * raster.px_per_mm)))
    toolpath = Toolpath(
        orientation="horizontal",
        clearance_z_mm=config.carving.clearance_z_mm,
        max_depth_mm=config.carving.max_depth_mm,
    )

    for y_mm in positions:
        row = raster.y_to_row(float(y_mm))
        cols = np.flatnonzero(mask[row, :])
        if cols.size < 2:
            continue
        c_left, c_right = int(cols[0]), int(cols[-1])

        col_range = np.arange(c_left, c_right + 1)
        x_values = np.asarray(raster.col_to_x(col_range), dtype=float)
        z_values, cut_flags = _build_profile(
            raster.darkness[row, c_left : c_right + 1],
            raster.mask[row, c_left : c_right + 1],
            config,
            raster.px_per_mm,
        )

        profile = simplify_profile(
            x_values, z_values, cut_flags, sample_step, config.simplification.rdp_tolerance
        )
        index = len(toolpath.lines)
        reverse = index % 2 == 1
        if reverse:
            profile = profile[::-1]

        points = np.column_stack(
            [profile[:, 0], np.full(len(profile), float(y_mm)), profile[:, 1]]
        )
        toolpath.lines.append(
            RasterLine(
                index=index,
                position_mm=float(y_mm),
                reversed_direction=reverse,
                points=points,
                raw_point_count=int(col_range.size),
                start_end="high" if reverse else "low",
                finish_end="low" if reverse else "high",
            )
        )
        toolpath.raw_point_count += int(col_range.size)

    return _finish_toolpath(toolpath)


def total_path_length_mm(toolpath: Toolpath) -> float:
    """Gesamtlaenge inklusive Verbindungen."""
    total = 0.0
    for _kind, points in toolpath.ordered_segments():
        total += polyline_length(points)
    return total
