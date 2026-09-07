"""STEP-Erzeugung, Rueckpruefung und STL."""

from __future__ import annotations

import numpy as np
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer

from app.models.config import ProjectConfig
from app.services.step_export import (
    StepExportError,
    analyse_free_edges,
    build_plate_solid,
    build_toolpath_wire,
    collect_free_edges,
    collect_solids,
    export_step,
    polyline_edge,
    read_step,
)
from app.services.step_validation import build_report
from app.services.stl_export import (
    build_relief_surface,
    export_plate_stl,
    export_relief_stl,
    validate_stl,
)
from app.services.tone_mapping import place_motif
from app.utils.occ import bbox_of


@pytest.fixture(scope="module")
def step_file(tmp_path_factory):
    """Einmal exportieren, danach von mehreren Tests lesen."""
    from app.services.image_cleanup import clean_image
    from app.services.motif_envelope import build_envelope
    from app.services.raster_paths import build_toolpath
    from tests.fixtures import transparent_motif_png_bytes

    config = ProjectConfig.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "STEP Test"},
            "plate": {"width_mm": 100, "height_mm": 80, "thickness_mm": 3, "margin_mm": 5},
            "carving": {"line_spacing_mm": 4, "motif_margin_mm": 5},
        }
    )
    motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
    raster = place_motif(motif, config)
    envelope = build_envelope(raster, config.carving.motif_margin_mm)
    toolpath = build_toolpath(raster, envelope, config)

    path = tmp_path_factory.mktemp("step") / "model.step"
    export_step(path, config, toolpath)
    return path, config, toolpath, raster


class TestPlateSolid:
    def test_referenzplatte_ist_gueltiger_solid(self, config: ProjectConfig):
        solid = build_plate_solid(config)
        assert BRepCheck_Analyzer(solid).IsValid()

    def test_abmessungen_und_lage(self, config: ProjectConfig):
        x0, y0, z0, x1, y1, z1 = bbox_of(build_plate_solid(config))
        assert (x1 - x0) == pytest.approx(config.plate.width_mm)
        assert (y1 - y0) == pytest.approx(config.plate.height_mm)
        assert (z1 - z0) == pytest.approx(config.plate.thickness_mm)
        assert z1 == pytest.approx(0.0), "Oberseite liegt auf Z0"
        assert z0 == pytest.approx(-config.plate.thickness_mm)
        assert (x0, y0) == pytest.approx((0.0, 0.0)), "Nullpunkt in der linken unteren Ecke"

    def test_flaechen_kanten_und_ecken_sind_vorhanden(self, config: ProjectConfig):
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer

        solid = build_plate_solid(config)

        def count(kind):
            explorer = TopExp_Explorer(solid, kind)
            total = 0
            while explorer.More():
                total += 1
                explorer.Next()
            return total

        assert count(TopAbs_FACE) == 6
        assert count(TopAbs_EDGE) == 24  # 12 Kanten, je Flaeche einmal referenziert
        assert count(TopAbs_VERTEX) == 48


class TestPolylineEdge:
    def test_zwei_punkte_ergeben_eine_gerade_kante(self):
        edge = polyline_edge(np.array([[0.0, 0.0, 1.0], [0.0, 10.0, 1.0]]))
        assert not edge.IsNull()

    def test_viele_punkte_ergeben_eine_einzige_kante(self):
        points = np.column_stack(
            [np.zeros(200), np.linspace(0, 50, 200), np.sin(np.linspace(0, 6, 200))]
        )
        edge = polyline_edge(points)
        x0, y0, z0, x1, y1, z1 = bbox_of(edge)
        assert y0 == pytest.approx(0.0, abs=1e-6)
        assert y1 == pytest.approx(50.0, abs=1e-6)

    def test_zu_wenige_punkte_werden_abgelehnt(self):
        with pytest.raises(StepExportError):
            polyline_edge(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]))


class TestStepRoundtrip:
    def test_datei_laesst_sich_wieder_oeffnen(self, step_file):
        path, _config, _toolpath, _raster = step_file
        assert path.stat().st_size > 0
        assert not read_step(path).IsNull()

    def test_enthaelt_genau_einen_gueltigen_solid(self, step_file):
        path, config, _toolpath, _raster = step_file
        solids = collect_solids(read_step(path))
        assert len(solids) == 1
        assert BRepCheck_Analyzer(solids[0]).IsValid()
        x0, y0, z0, x1, y1, z1 = bbox_of(solids[0])
        assert (x1 - x0) == pytest.approx(config.plate.width_mm, abs=1e-3)
        assert (y1 - y0) == pytest.approx(config.plate.height_mm, abs=1e-3)

    def test_enthaelt_die_bahn_als_freie_kanten(self, step_file):
        path, _config, toolpath, _raster = step_file
        edges = collect_free_edges(read_step(path))
        assert len(edges) == len(toolpath.lines) + len(toolpath.connectors)

    def test_bahn_ist_zusammenhaengend(self, step_file):
        path, _config, toolpath, _raster = step_file
        analysis = analyse_free_edges(collect_free_edges(read_step(path)), toolpath.orientation)
        assert analysis["connected"] is True
        assert analysis["open_ends"] == 2
        assert analysis["branch_nodes"] == 0

    def test_linien_und_verbindungen_werden_korrekt_gezaehlt(self, step_file):
        path, _config, toolpath, _raster = step_file
        analysis = analyse_free_edges(collect_free_edges(read_step(path)), toolpath.orientation)
        assert analysis["line_edges"] == len(toolpath.lines)
        assert analysis["connector_edges"] == len(toolpath.connectors)

    def test_z_bereich_der_bahn(self, step_file):
        path, config, _toolpath, _raster = step_file
        boxes = np.array([bbox_of(edge) for edge in collect_free_edges(read_step(path))])
        assert boxes[:, 5].max() == pytest.approx(config.carving.clearance_z_mm, abs=1e-3)
        assert boxes[:, 2].min() >= -config.carving.max_depth_mm - 1e-3

    def test_wire_ohne_linien_wird_abgelehnt(self):
        from app.services.raster_paths import Toolpath

        with pytest.raises(StepExportError):
            build_toolpath_wire(Toolpath())


class TestReport:
    def test_vollstaendiger_bericht_besteht(self, step_file):
        path, config, toolpath, raster = step_file
        metrics = toolpath.metrics(config, raster)
        report = build_report("job", config, toolpath, metrics, path)
        failed = [check.name for check in report.checks if not check.passed]
        assert failed == [], f"Fehlgeschlagene Pruefungen: {failed}"
        assert report.passed is True
        assert len(report.checks) >= 20

    def test_bericht_enthaelt_alle_kernpruefungen(self, step_file):
        path, config, toolpath, raster = step_file
        report = build_report("job", config, toolpath, toolpath.metrics(config, raster), path)
        names = {check.name for check in report.checks}
        for expected in {
            "step_lesbar",
            "referenzplatte_gueltig",
            "plattenabmessungen",
            "bahn_zusammenhaengend",
            "anzahl_rasterlinien",
            "anzahl_verbindungen",
            "step_z_maximum",
            "step_z_minimum",
            "keine_spiegelung",
            "keine_leeren_koerper",
            "punktreduktion",
            "keine_langen_rueckfahrten",
        }:
            assert expected in names

    def test_bericht_meldet_fehlende_datei(self, tmp_path, step_file):
        _path, config, toolpath, raster = step_file
        report = build_report(
            "job", config, toolpath, toolpath.metrics(config, raster), tmp_path / "fehlt.step"
        )
        assert report.passed is False
        assert any(check.name == "step_lesbar" and not check.passed for check in report.checks)

    def test_bericht_enthaelt_warnhinweis(self, step_file):
        path, config, toolpath, raster = step_file
        report = build_report("job", config, toolpath, toolpath.metrics(config, raster), path)
        assert "Simulation" in report.disclaimer


class TestStl:
    def test_platte_ist_wasserdicht(self, tmp_path, config: ProjectConfig):
        path = tmp_path / "plate.stl"
        export_plate_stl(path, config)
        info = validate_stl(path)
        assert info["watertight"] is True
        assert info["consistently_oriented"] is True
        assert info["triangle_count"] == 12
        assert info["volume_mm3"] == pytest.approx(
            config.plate.width_mm * config.plate.height_mm * config.plate.thickness_mm
        )

    def test_relief_ist_wasserdicht_und_haelt_die_plattenstaerke(self, tmp_path):
        from app.services.image_cleanup import clean_image
        from tests.fixtures import transparent_motif_png_bytes

        config = ProjectConfig.model_validate(
            {
                "schema_version": "1.0",
                "mode": "relief",
                "plate": {"width_mm": 60, "height_mm": 50, "thickness_mm": 4, "margin_mm": 5},
                "relief": {"height_mm": 2.0, "base_thickness_mm": 1.0, "sample_distance_mm": 0.5},
            }
        )
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        surface = build_relief_surface(raster, config)

        path = tmp_path / "relief.stl"
        export_relief_stl(path, surface)
        info = validate_stl(path)

        assert info["watertight"] is True
        assert info["consistently_oriented"] is True
        assert info["non_manifold_edges"] == 0
        assert info["size_mm"][0] == pytest.approx(config.plate.width_mm, abs=0.01)
        assert info["size_mm"][1] == pytest.approx(config.plate.height_mm, abs=0.01)
        assert info["size_mm"][2] <= config.plate.thickness_mm + 1e-6
        assert info["bbox_max_mm"][2] <= config.plate.top_z_mm + 1e-6

    def test_relief_hoehe_bleibt_im_rahmen(self):
        with pytest.raises(ValueError, match="thickness_mm"):
            ProjectConfig.model_validate(
                {
                    "schema_version": "1.0",
                    "mode": "relief",
                    "plate": {"thickness_mm": 3},
                    "relief": {"height_mm": 3.0, "base_thickness_mm": 1.0},
                }
            )

    def test_invert_dreht_die_hoehen_um(self):
        from app.services.image_cleanup import clean_image
        from tests.fixtures import transparent_motif_png_bytes

        base = ProjectConfig.model_validate(
            {"schema_version": "1.0", "mode": "relief", "plate": {"width_mm": 60, "height_mm": 50}}
        )
        inverted = base.model_copy(deep=True)
        inverted.relief.invert = True

        motif = clean_image(transparent_motif_png_bytes(), base.cleanup)
        raster = place_motif(motif, base)
        normal_heights = build_relief_surface(raster, base).heights_mm
        inverted_heights = build_relief_surface(raster, inverted).heights_mm
        assert normal_heights.max() > 0 and inverted_heights.max() > 0
        assert not np.allclose(normal_heights, inverted_heights)

    def test_grosses_relief_wird_vergroebert(self):
        from app.services.image_cleanup import clean_image
        from tests.fixtures import transparent_motif_png_bytes

        config = ProjectConfig.model_validate(
            {
                "schema_version": "1.0",
                "mode": "relief",
                "plate": {"width_mm": 400, "height_mm": 400},
                "relief": {"sample_distance_mm": 0.1},
            }
        )
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        surface = build_relief_surface(place_motif(motif, config), config)
        assert surface.effective_sample_distance_mm > config.relief.sample_distance_mm
        assert surface.heights_mm.size <= 160_000
