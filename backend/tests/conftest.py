"""Gemeinsame Test-Fixtures.

Das Datenverzeichnis wird pro Testlauf umgebogen, damit keine Jobdateien im
Projektverzeichnis landen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir(tmp_path_factory: pytest.TempPathFactory) -> None:
    os.environ["VCUTTING_DATA_DIR"] = str(tmp_path_factory.mktemp("vcutting-data"))


@pytest.fixture
def config():
    from app.models.config import ProjectConfig

    return ProjectConfig()


@pytest.fixture
def small_config():
    """Kleine Platte, damit die Geometrietests schnell laufen."""
    from app.models.config import ProjectConfig

    return ProjectConfig.model_validate(
        {
            "schema_version": "1.0",
            "project": {"name": "Test"},
            "plate": {"width_mm": 100, "height_mm": 80, "thickness_mm": 3, "margin_mm": 5},
            "carving": {"line_spacing_mm": 3, "motif_margin_mm": 5},
        }
    )


@pytest.fixture
def pipeline(small_config):
    """Vollstaendige Pipeline bis zur Bahn, ohne Dateiausgabe."""
    from app.services.image_cleanup import clean_image
    from app.services.motif_envelope import build_envelope
    from app.services.raster_paths import build_toolpath
    from app.services.tone_mapping import place_motif
    from tests.fixtures import transparent_motif_png_bytes

    motif = clean_image(transparent_motif_png_bytes(), small_config.cleanup)
    raster = place_motif(motif, small_config)
    envelope = build_envelope(raster, small_config.carving.motif_margin_mm)
    toolpath = build_toolpath(raster, envelope, small_config)
    return small_config, motif, raster, envelope, toolpath


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
