"""Werkzeuggeometrie und Vereinfachungsalgorithmen."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.models.config import ProjectConfig
from app.services.simplify_paths import profile_keypoints, reduction_percent, simplify_profile
from app.utils.geometry import (
    dedupe_consecutive,
    depth_for_groove_width_mm,
    groove_width_mm,
    polyline_length,
    rdp,
    remaining_thickness_mm,
)


class TestGrooveWidth:
    def test_90_grad_ergibt_doppelte_tiefe(self):
        # tan(45 Grad) = 1, also Nutbreite = 2 * Tiefe
        assert groove_width_mm(1.2, 90.0) == pytest.approx(2.4)
        assert groove_width_mm(0.5, 90.0) == pytest.approx(1.0)

    def test_60_grad_ist_schmaler_als_90_grad(self):
        assert groove_width_mm(1.0, 60.0) < groove_width_mm(1.0, 90.0)
        assert groove_width_mm(1.0, 60.0) == pytest.approx(2 * math.tan(math.radians(30)))

    def test_120_grad_ist_breiter_als_90_grad(self):
        assert groove_width_mm(1.0, 120.0) > groove_width_mm(1.0, 90.0)

    def test_umkehrung(self):
        assert depth_for_groove_width_mm(groove_width_mm(0.8, 75.0), 75.0) == pytest.approx(0.8)

    def test_ungueltige_winkel_werden_abgelehnt(self):
        with pytest.raises(ValueError):
            groove_width_mm(1.0, 0.0)
        with pytest.raises(ValueError):
            groove_width_mm(1.0, 180.0)

    def test_config_property_stimmt_mit_formel_ueberein(self):
        config = ProjectConfig()
        assert config.groove_width_mm == pytest.approx(
            groove_width_mm(config.carving.max_depth_mm, config.tool.angle_deg)
        )


class TestRemainingThickness:
    def test_reststaerke(self):
        assert remaining_thickness_mm(3.0, 1.2) == pytest.approx(1.8)

    def test_config_warnt_bei_geringer_reststaerke(self):
        config = ProjectConfig.model_validate(
            {
                "schema_version": "1.0",
                "plate": {"thickness_mm": 3.0},
                "carving": {"max_depth_mm": 2.8, "line_spacing_mm": 6.0},
            }
        )
        assert config.remaining_thickness_mm == pytest.approx(0.2)
        assert any("Reststaerke" in warning for warning in config.warnings())

    def test_config_warnt_bei_ueberschneidenden_nuten(self):
        config = ProjectConfig.model_validate(
            {"schema_version": "1.0", "carving": {"max_depth_mm": 1.2, "line_spacing_mm": 1.0}}
        )
        assert any("Nutbreite" in warning for warning in config.warnings())

    def test_tiefe_darf_platte_nicht_durchtrennen(self):
        with pytest.raises(ValueError, match="max_depth_mm"):
            ProjectConfig.model_validate(
                {"schema_version": "1.0", "plate": {"thickness_mm": 3.0}, "carving": {"max_depth_mm": 3.0}}
            )


class TestRdp:
    def test_gerade_wird_auf_zwei_punkte_reduziert(self):
        points = np.column_stack([np.linspace(0, 10, 101), np.zeros(101)])
        assert len(rdp(points, 0.01)) == 2

    def test_ecke_bleibt_erhalten(self):
        points = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [2.0, 5.0], [2.0, 10.0]])
        simplified = rdp(points, 0.05)
        assert len(simplified) == 3
        assert simplified[1].tolist() == [2.0, 0.0]

    def test_rauschen_unter_toleranz_verschwindet(self):
        rng = np.random.default_rng(3)
        t = np.linspace(0, 50, 2000)
        z = rng.normal(0, 0.02, 2000)
        simplified = rdp(np.column_stack([t, z]), 0.18)
        assert len(simplified) < 20

    def test_endpunkte_bleiben_immer(self):
        points = np.column_stack([np.linspace(0, 5, 50), np.sin(np.linspace(0, 5, 50))])
        simplified = rdp(points, 0.5)
        assert simplified[0].tolist() == points[0].tolist()
        assert simplified[-1].tolist() == points[-1].tolist()

    def test_reduziert_niemals_unter_zwei_punkte(self):
        assert len(rdp(np.array([[0.0, 0.0], [1.0, 1.0]]), 10.0)) == 2


class TestProfileSimplification:
    def _profile(self, n=400):
        t = np.linspace(0.0, 100.0, n)
        cut = (t > 25.0) & (t < 75.0)
        z = np.where(cut, -1.2, 1.0)
        return t, z, cut

    def test_zustandswechsel_bleiben_erhalten(self):
        t, z, cut = self._profile()
        keep = profile_keypoints(z, cut, step=8)
        changes = np.flatnonzero(np.diff(cut.astype(int)) != 0)
        for index in changes:
            assert keep[index] and keep[index + 1]

    def test_starke_vereinfachung_reduziert_deutlich(self):
        t, z, cut = self._profile()
        simplified = simplify_profile(t, z, cut, sample_step_px=8, rdp_tolerance_mm=0.18)
        assert len(simplified) < 10
        assert reduction_percent(len(t), len(simplified)) > 95.0

    def test_maximale_tiefe_bleibt_erhalten(self):
        t = np.linspace(0.0, 40.0, 400)
        cut = np.ones_like(t, dtype=bool)
        z = -0.2 - 1.0 * np.exp(-((t - 20.0) ** 2) / 2.0)
        simplified = simplify_profile(t, z, cut, sample_step_px=8, rdp_tolerance_mm=0.18)
        assert simplified[:, 1].min() <= z.min() + 0.18

    def test_endpunkte_bleiben_erhalten(self):
        t, z, cut = self._profile()
        simplified = simplify_profile(t, z, cut, sample_step_px=8, rdp_tolerance_mm=0.18)
        assert simplified[0, 0] == pytest.approx(t[0])
        assert simplified[-1, 0] == pytest.approx(t[-1])
        assert simplified[0, 1] == pytest.approx(1.0)
        assert simplified[-1, 1] == pytest.approx(1.0)

    def test_reduktion_prozent(self):
        assert reduction_percent(1000, 100) == pytest.approx(90.0)
        assert reduction_percent(0, 0) == 0.0


class TestHelpers:
    def test_dedupe_entfernt_doppelte_punkte(self):
        points = np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        assert len(dedupe_consecutive(points)) == 3

    def test_polyline_laenge(self):
        assert polyline_length(np.array([[0.0, 0.0], [3.0, 4.0]])) == pytest.approx(5.0)
        assert polyline_length(np.array([[0.0, 0.0]])) == 0.0
