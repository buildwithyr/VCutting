"""Projektformat, Validierung und HTTP-Schnittstelle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.config import (
    SCHEMA_VERSION,
    SIMPLIFICATION_PRESETS,
    ProjectConfig,
    migrate_project_dict,
)
from app.utils.filenames import safe_job_id, safe_slug, upload_suffix
from tests.fixtures import corrupt_png_bytes, transparent_motif_png_bytes

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "shared" / "schemas" / "vcutting-project-1.0.schema.json"
)


class TestProjectConfig:
    def test_standardwerte_entsprechen_der_spezifikation(self):
        config = ProjectConfig()
        assert config.plate.width_mm == 400
        assert config.plate.height_mm == 400
        assert config.plate.thickness_mm == 3
        assert config.plate.margin_mm == 20
        assert config.tool.id == "T246"
        assert config.tool.angle_deg == 90
        assert config.carving.max_depth_mm == 1.2
        assert config.carving.line_spacing_mm == 2
        assert config.carving.orientation == "vertical"
        assert config.carving.path_mode == "serpentine"
        assert config.carving.clearance_z_mm == 1
        assert config.carving.motif_margin_mm == 5
        assert config.carving.tone_threshold == 0.055
        assert config.carving.depth_gamma == 1.0
        assert config.simplification.mode == "catia_strong"

    def test_vereinfachungsstufen_werden_vorbelegt(self):
        for mode, preset in SIMPLIFICATION_PRESETS.items():
            config = ProjectConfig.model_validate(
                {"schema_version": "1.0", "simplification": {"mode": mode}}
            )
            assert config.simplification.sample_distance_mm == preset["sample_distance_mm"]
            assert config.simplification.rdp_tolerance_mm == preset["rdp_tolerance_mm"]
            assert config.simplification.smoothing_distance_mm == preset["smoothing_distance_mm"]

    def test_starke_stufe_hat_die_geforderten_werte(self):
        simplification = ProjectConfig().simplification
        assert simplification.sample_distance_mm == 2.0
        assert simplification.smoothing_distance_mm == 2.0
        assert simplification.rdp_tolerance_mm == 0.18
        assert simplification.target_reduction_percent == 90.0

    def test_eigene_werte_ueberschreiben_die_vorbelegung(self):
        config = ProjectConfig.model_validate(
            {"schema_version": "1.0", "simplification": {"mode": "catia_strong", "rdp_tolerance_mm": 0.5}}
        )
        assert config.simplification.rdp_tolerance_mm == 0.5
        assert config.simplification.sample_distance_mm == 2.0

    @pytest.mark.parametrize(
        "payload",
        [
            {"plate": {"width_mm": 0}},
            {"plate": {"width_mm": -400}},
            {"plate": {"thickness_mm": 0}},
            {"plate": {"margin_mm": 250}},
            {"tool": {"angle_deg": 0}},
            {"tool": {"angle_deg": 180}},
            {"carving": {"max_depth_mm": 0}},
            {"carving": {"line_spacing_mm": 0}},
            {"carving": {"clearance_z_mm": 0}},
            {"carving": {"tone_threshold": 1.5}},
            {"carving": {"depth_gamma": 0}},
            {"carving": {"orientation": "diagonal"}},
            {"carving": {"path_mode": "zigzag"}},
            {"simplification": {"mode": "ultra"}},
            {"unbekanntes_feld": 1},
        ],
    )
    def test_ungueltige_eingaben_werden_abgelehnt(self, payload):
        with pytest.raises(ValueError):
            ProjectConfig.model_validate({"schema_version": "1.0", **payload})

    def test_ex_und_import_sind_verlustfrei(self):
        original = ProjectConfig.model_validate(
            {
                "schema_version": "1.0",
                "project": {"name": "Oskar"},
                "plate": {"width_mm": 300, "height_mm": 200, "thickness_mm": 6, "margin_mm": 10},
                "tool": {"id": "T101", "name": "V 60", "type": "v_bit", "angle_deg": 60},
                "carving": {"max_depth_mm": 2.0, "line_spacing_mm": 1.5},
                "simplification": {"mode": "catia_normal"},
            }
        )
        roundtrip = ProjectConfig.model_validate(json.loads(original.model_dump_json()))
        assert roundtrip == original


class TestMigration:
    def test_aktuelle_version_bleibt_unveraendert(self):
        data = {"schema_version": SCHEMA_VERSION, "project": {"name": "x"}}
        assert migrate_project_dict(data) == data

    def test_fehlende_version_wird_ergaenzt(self):
        assert migrate_project_dict({"project": {"name": "x"}})["schema_version"] == SCHEMA_VERSION

    def test_unbekannte_version_wird_abgelehnt(self):
        with pytest.raises(ValueError, match="9.9"):
            migrate_project_dict({"schema_version": "9.9"})

    def test_kein_objekt_wird_abgelehnt(self):
        with pytest.raises(ValueError):
            migrate_project_dict(["kein", "objekt"])  # type: ignore[arg-type]


class TestSharedSchema:
    def test_schema_datei_existiert_und_ist_gueltiges_json(self):
        assert SCHEMA_PATH.exists(), f"{SCHEMA_PATH} fehlt"
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION

    def test_schema_kennt_alle_hauptabschnitte(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert set(ProjectConfig.model_fields) <= set(schema["properties"])


class TestFilenames:
    def test_gefaehrliche_zeichen_werden_ersetzt(self):
        assert "/" not in safe_slug("../../etc/passwd")
        assert safe_slug("Oskar V-Cutting") == "Oskar-V-Cutting"
        assert safe_slug("") == "projekt"
        assert safe_slug("...") == "projekt"

    def test_job_id_muss_uuid_sein(self):
        valid = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
        assert safe_job_id(valid) == valid
        for bad in ["../../etc", "not-a-uuid", "", None, "3f2504e0"]:
            with pytest.raises(ValueError):
                safe_job_id(bad)

    def test_dateiendung_folgt_dem_inhalt_nicht_dem_namen(self):
        assert upload_suffix("bild.exe", "PNG") == ".png"
        assert upload_suffix("bild.png", "JPEG") == ".jpg"
        assert upload_suffix("../../x.sh", None) == ".png"


class TestApi:
    def test_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["schema_version"] == SCHEMA_VERSION
        assert body["occ_available"] is True

    def test_defaults(self, client):
        body = client.get("/api/config/defaults").json()
        assert body["defaults"]["tool"]["id"] == "T246"
        assert "catia_strong" in body["simplification_presets"]

    def test_config_validate_ergaenzt_vorbelegungen(self, client):
        response = client.post(
            "/api/config/validate", json={"schema_version": "1.0", "simplification": {"mode": "fine"}}
        )
        assert response.status_code == 200
        assert response.json()["simplification"]["rdp_tolerance_mm"] == 0.03

    def test_config_validate_lehnt_muell_ab(self, client):
        response = client.post("/api/config/validate", json={"schema_version": "1.0", "plate": {"width_mm": -1}})
        assert response.status_code == 422

    def test_vollstaendiger_job(self, client):
        config = {
            "schema_version": "1.0",
            "project": {"name": "API Test"},
            "plate": {"width_mm": 100, "height_mm": 80, "thickness_mm": 3, "margin_mm": 5},
            "carving": {"line_spacing_mm": 4},
            "output": {"include_reference_plate": True, "step": True, "stl": True, "preview_png": True},
        }
        response = client.post(
            "/api/jobs",
            files={"image": ("motiv.png", transparent_motif_png_bytes(), "image/png")},
            data={"config": json.dumps(config)},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # BackgroundTasks laufen im TestClient synchron nach der Antwort.
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "completed"
        assert job["progress"] == 1.0
        assert job["report_passed"] is True
        assert job["metrics"]["reduction_percent"] >= 85.0
        assert job["metrics"]["connector_count"] == job["metrics"]["line_count"] - 1

        assert all(job["artifacts"].values())

        for endpoint, media in [
            ("preview/cleaned", "image/png"),
            ("preview/toolpath", "image/png"),
            ("preview/simulation", "image/png"),
            ("download/project", "application/json"),
            ("download/step", "model/step"),
            ("download/stl", "model/stl"),
        ]:
            download = client.get(f"/api/jobs/{job_id}/{endpoint}")
            assert download.status_code == 200, endpoint
            assert download.headers["content-type"].startswith(media.split("/")[0])
            assert len(download.content) > 0

        report = client.get(f"/api/jobs/{job_id}/report").json()
        assert report["passed"] is True
        assert "Simulation" in report["disclaimer"]

        # Die Projektdatei laesst sich wieder einlesen.
        project = json.loads(client.get(f"/api/jobs/{job_id}/download/project").content)
        assert ProjectConfig.model_validate(project).project.name == "API Test"

        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404

    def test_job_ohne_konfiguration_nutzt_standardwerte(self, client):
        response = client.post(
            "/api/jobs",
            files={"image": ("m.png", transparent_motif_png_bytes(160, 120), "image/png")},
        )
        assert response.status_code == 202
        job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
        assert job["config"]["plate"]["width_mm"] == 400
        assert job["status"] == "completed"

    def test_beschaedigter_upload_wird_abgelehnt(self, client):
        response = client.post(
            "/api/jobs", files={"image": ("kaputt.png", corrupt_png_bytes(), "image/png")}
        )
        assert response.status_code == 422
        assert "beschaedigt" in response.json()["detail"] or "Bild" in response.json()["detail"]

    def test_mime_type_wird_nicht_geglaubt(self, client):
        """Als PNG deklarierter Text muss trotzdem abgelehnt werden."""
        response = client.post(
            "/api/jobs", files={"image": ("trick.png", b"#!/bin/sh\nrm -rf /\n" * 20, "image/png")}
        )
        assert response.status_code == 422

    def test_ungueltige_konfiguration_wird_abgelehnt(self, client):
        response = client.post(
            "/api/jobs",
            files={"image": ("m.png", transparent_motif_png_bytes(), "image/png")},
            data={"config": json.dumps({"schema_version": "1.0", "carving": {"max_depth_mm": 99}})},
        )
        assert response.status_code == 422

    def test_kaputtes_json_wird_abgelehnt(self, client):
        response = client.post(
            "/api/jobs",
            files={"image": ("m.png", transparent_motif_png_bytes(), "image/png")},
            data={"config": "{nicht wirklich json"},
        )
        assert response.status_code == 422
        assert "JSON" in str(response.json()["detail"])

    def test_pfadmanipulation_ueber_job_id(self, client):
        assert client.get("/api/jobs/not-a-uuid").status_code == 400
        assert client.get("/api/jobs/..%2F..%2Fetc").status_code in (400, 404)
        assert client.delete("/api/jobs/not-a-uuid").status_code == 400

    def test_unbekannter_job(self, client):
        missing = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
        assert client.get(f"/api/jobs/{missing}").status_code == 404
        assert client.get(f"/api/jobs/{missing}/download/step").status_code == 404
        assert client.delete(f"/api/jobs/{missing}").status_code == 404

    def test_fehlgeschlagener_job_meldet_den_grund(self, client):
        """Ein vollstaendig transparentes Bild enthaelt kein Motiv."""
        import io

        import numpy as np
        from PIL import Image

        buffer = io.BytesIO()
        Image.fromarray(np.zeros((80, 80, 4), dtype=np.uint8), mode="RGBA").save(buffer, format="PNG")

        response = client.post("/api/jobs", files={"image": ("leer.png", buffer.getvalue(), "image/png")})
        assert response.status_code == 202
        job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
        assert job["status"] == "failed"
        assert job["error"]
        assert "Motiv" in job["error"]
