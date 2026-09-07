"""Motivbegrenzte Rasterlinien und Schlangenbahn."""

from __future__ import annotations

import numpy as np
import pytest

from app.models.config import MIN_ACCEPTABLE_REDUCTION_PERCENT
from app.services.image_cleanup import clean_image
from app.services.motif_envelope import build_envelope
from app.services.raster_paths import build_toolpath
from app.services.tone_mapping import place_motif
from tests.fixtures import transparent_motif_png_bytes


class TestSerpentine:
    def test_richtung_wechselt(self, pipeline):
        _config, _motif, _raster, _envelope, toolpath = pipeline
        assert len(toolpath.lines) > 4
        for index, line in enumerate(toolpath.lines):
            assert line.reversed_direction == (index % 2 == 1)

    def test_erste_linie_laeuft_von_oben_nach_unten(self, pipeline):
        _config, _motif, _raster, _envelope, toolpath = pipeline
        first = toolpath.lines[0].points
        assert first[0][1] > first[-1][1]

    def test_zweite_linie_laeuft_von_unten_nach_oben(self, pipeline):
        _config, _motif, _raster, _envelope, toolpath = pipeline
        second = toolpath.lines[1].points
        assert second[0][1] < second[-1][1]

    def test_verbindungen_anzahl(self, pipeline):
        _config, _motif, _raster, _envelope, toolpath = pipeline
        assert len(toolpath.connectors) == len(toolpath.lines) - 1

    def test_verbindungen_liegen_auf_sicherheits_z(self, pipeline):
        config, _motif, _raster, _envelope, toolpath = pipeline
        clearance = config.carving.clearance_z_mm
        for connector in toolpath.connectors:
            assert connector.start[2] == pytest.approx(clearance)
            assert connector.end[2] == pytest.approx(clearance)

    def test_verbindungen_schliessen_luecken_exakt(self, pipeline):
        _config, _motif, _raster, _envelope, toolpath = pipeline
        for index, connector in enumerate(toolpath.connectors):
            assert np.allclose(connector.start, toolpath.lines[index].points[-1])
            assert np.allclose(connector.end, toolpath.lines[index + 1].points[0])

    def test_keine_langen_diagonalen_rueckfahrten(self, pipeline):
        config, _motif, _raster, _envelope, toolpath = pipeline
        points = toolpath.polyline()
        motif_height = points[:, 1].max() - points[:, 1].min()
        longest = max(connector.length_mm for connector in toolpath.connectors)
        # Eine echte Rasterrueckfahrt waere so lang wie das Motiv hoch ist.
        assert longest < 0.25 * motif_height
        # Der X-Anteil jeder Verbindung entspricht genau einem Linienabstand.
        for connector in toolpath.connectors:
            dx = abs(connector.end[0] - connector.start[0])
            assert dx == pytest.approx(config.carving.line_spacing_mm, abs=0.05)

    def test_verbindungen_wechseln_zwischen_oben_und_unten(self, pipeline):
        _config, _motif, _raster, _envelope, toolpath = pipeline
        sides = [connector.end_side for connector in toolpath.connectors]
        assert sides[0] == "low"
        for previous, following in zip(sides, sides[1:], strict=False):
            assert previous != following

    def test_jede_linie_beginnt_und_endet_auf_sicherheits_z(self, pipeline):
        config, _motif, _raster, _envelope, toolpath = pipeline
        clearance = config.carving.clearance_z_mm
        for line in toolpath.lines:
            assert line.points[0][2] == pytest.approx(clearance)
            assert line.points[-1][2] == pytest.approx(clearance)

    def test_linien_haben_konstantes_x(self, pipeline):
        _config, _motif, _raster, _envelope, toolpath = pipeline
        for line in toolpath.lines:
            assert np.ptp(line.points[:, 0]) == pytest.approx(0.0, abs=1e-9)

    def test_linienabstand_wird_eingehalten(self, pipeline):
        config, _motif, _raster, _envelope, toolpath = pipeline
        positions = np.array([line.position_mm for line in toolpath.lines])
        gaps = np.diff(positions)
        assert np.allclose(gaps, config.carving.line_spacing_mm, atol=0.05)


class TestMotifBounded:
    def test_bahn_bleibt_innerhalb_der_motivhuelle(self, pipeline):
        config, _motif, raster, envelope, toolpath = pipeline
        points = toolpath.polyline()
        for x_mm, y_mm, _z in points:
            col = raster.x_to_col(float(x_mm))
            row = raster.y_to_row(float(y_mm))
            assert envelope.mask[row, col], f"Punkt ({x_mm:.2f}, {y_mm:.2f}) liegt ausserhalb der Huelle"

    def test_rechteckiger_hintergrund_wird_nicht_ueberfahren(self, pipeline):
        """Die Bahn darf die Plattenecken nicht erreichen."""
        config, _motif, raster, _envelope, toolpath = pipeline
        points = toolpath.polyline()
        x0, y0, x1, y1 = raster.motif_bbox_mm
        margin = config.carving.motif_margin_mm
        assert points[:, 0].min() >= x0 - margin - 1.0
        assert points[:, 0].max() <= x1 + margin + 1.0
        assert points[:, 1].min() >= y0 - margin - 1.0
        assert points[:, 1].max() <= y1 + margin + 1.0

    def test_es_wird_nur_innerhalb_des_motivs_gefraest(self, pipeline):
        _config, _motif, raster, _envelope, toolpath = pipeline
        for line in toolpath.lines:
            for x_mm, y_mm, z_mm in line.points:
                if z_mm < 0:
                    col = raster.x_to_col(float(x_mm))
                    row = raster.y_to_row(float(y_mm))
                    assert raster.mask[row, col], "Es wird ausserhalb der Motivkontur geschnitten"

    def test_groesserer_rand_erzeugt_mehr_linien(self, small_config):
        motif = clean_image(transparent_motif_png_bytes(), small_config.cleanup)
        raster = place_motif(motif, small_config)
        wenig = build_toolpath(raster, build_envelope(raster, 0.0), small_config)
        viel = build_toolpath(raster, build_envelope(raster, 8.0), small_config)
        assert len(viel.lines) > len(wenig.lines)


class TestDepth:
    def test_maximale_tiefe_wird_eingehalten(self, pipeline):
        config, _motif, _raster, _envelope, toolpath = pipeline
        points = toolpath.polyline()
        assert points[:, 2].min() >= -config.carving.max_depth_mm - 1e-9

    def test_sicherheitshoehe_ist_das_z_maximum(self, pipeline):
        config, _motif, _raster, _envelope, toolpath = pipeline
        points = toolpath.polyline()
        assert points[:, 2].max() == pytest.approx(config.carving.clearance_z_mm)

    def test_helle_stellen_liegen_auf_sicherheits_z(self, pipeline):
        config, _motif, raster, _envelope, toolpath = pipeline
        clearance = config.carving.clearance_z_mm
        angehoben = 0
        for line in toolpath.lines:
            for _x, _y, z_mm in line.points:
                if z_mm == pytest.approx(clearance):
                    angehoben += 1
        assert angehoben > 2 * len(toolpath.lines), "Helle Bereiche muessen angehoben werden"

    def test_dunkler_bereich_wird_tiefer_gefraest(self, pipeline):
        config, _motif, _raster, _envelope, toolpath = pipeline
        points = toolpath.polyline()
        cut = points[points[:, 2] < 0]
        assert len(cut) > 0
        deepest = cut[np.argmin(cut[:, 2])]
        # Das dunkle Quadrat sitzt oben links.
        assert deepest[0] < config.plate.width_mm / 2
        assert deepest[1] > config.plate.height_mm / 2


class TestMetrics:
    def test_starke_vereinfachung_erreicht_hohe_reduktion(self, pipeline):
        config, _motif, raster, _envelope, toolpath = pipeline
        metrics = toolpath.metrics(config, raster)
        assert metrics.raw_point_count > metrics.simplified_point_count
        assert metrics.reduction_percent >= MIN_ACCEPTABLE_REDUCTION_PERCENT

    def test_normale_stufe_erzeugt_mehr_punkte_als_starke(self, small_config):
        motif = clean_image(transparent_motif_png_bytes(), small_config.cleanup)
        raster = place_motif(motif, small_config)
        envelope = build_envelope(raster, small_config.carving.motif_margin_mm)
        strong = build_toolpath(raster, envelope, small_config).metrics(small_config, raster)

        normal_config = small_config.model_copy(deep=True)
        normal_config.simplification = type(small_config.simplification)(mode="catia_normal")
        normal = build_toolpath(raster, envelope, normal_config).metrics(normal_config, raster)

        assert normal.simplified_point_count > strong.simplified_point_count

    def test_kennzahlen_sind_konsistent(self, pipeline):
        config, _motif, raster, _envelope, toolpath = pipeline
        metrics = toolpath.metrics(config, raster)
        assert metrics.line_count == len(toolpath.lines)
        assert metrics.connector_count == len(toolpath.lines) - 1
        assert metrics.simplified_point_count == sum(
            line.point_count for line in toolpath.lines
        )
        assert metrics.max_points_per_line >= metrics.avg_points_per_line
        assert metrics.estimated_step_size_kb > 0
        assert metrics.groove_width_mm == pytest.approx(config.groove_width_mm)


class TestHorizontalOrientation:
    @pytest.fixture
    def horizontal(self, small_config):
        config = small_config.model_copy(deep=True)
        config.carving.orientation = "horizontal"
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        envelope = build_envelope(raster, config.carving.motif_margin_mm)
        return config, raster, build_toolpath(raster, envelope, config)

    def test_linien_haben_konstantes_y(self, horizontal):
        _config, _raster, toolpath = horizontal
        for line in toolpath.lines:
            assert np.ptp(line.points[:, 1]) == pytest.approx(0.0, abs=1e-9)

    def test_richtung_wechselt_auch_horizontal(self, horizontal):
        _config, _raster, toolpath = horizontal
        first, second = toolpath.lines[0].points, toolpath.lines[1].points
        assert first[0][0] < first[-1][0]
        assert second[0][0] > second[-1][0]

    def test_verbindungen_bleiben_kurz(self, horizontal):
        config, _raster, toolpath = horizontal
        for connector in toolpath.connectors:
            dy = abs(connector.end[1] - connector.start[1])
            assert dy == pytest.approx(config.carving.line_spacing_mm, abs=0.05)
