"""Bildbereinigung, Platzierung und Tonwertabbildung."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from app.models.config import Cleanup, ProjectConfig
from app.services.image_cleanup import MotifNotFound, clean_image
from app.services.motif_envelope import build_envelope, dilate_mask_mm
from app.services.tone_mapping import place_motif
from app.utils.validation import UploadRejected, validate_image_bytes
from tests.fixtures import (
    add_speckles,
    asymmetric_motif_rgba,
    corrupt_png_bytes,
    opaque_motif_png_bytes,
    to_png_bytes,
    transparent_motif_png_bytes,
)


class TestUploadValidation:
    def test_gueltiges_png_wird_akzeptiert(self):
        info = validate_image_bytes(transparent_motif_png_bytes())
        assert info.image_format == "PNG"
        assert info.has_alpha is True

    def test_beschaedigtes_bild_wird_abgelehnt(self):
        with pytest.raises(UploadRejected):
            validate_image_bytes(corrupt_png_bytes())

    def test_leere_datei_wird_abgelehnt(self):
        with pytest.raises(UploadRejected, match="leer"):
            validate_image_bytes(b"")

    def test_nicht_bild_wird_abgelehnt(self):
        with pytest.raises(UploadRejected):
            validate_image_bytes(b"<html>kein Bild</html>" * 20)

    def test_zu_grosse_datei_wird_abgelehnt(self):
        with pytest.raises(UploadRejected, match="MB"):
            validate_image_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (21 * 1024 * 1024))

    def test_unerlaubtes_format_wird_abgelehnt(self):
        buffer = io.BytesIO()
        Image.new("RGB", (32, 32), "white").save(buffer, format="BMP")
        with pytest.raises(UploadRejected, match="nicht unterstuetzt"):
            validate_image_bytes(buffer.getvalue())


class TestCleanup:
    def test_transparenter_hintergrund_wird_ausgeschlossen(self):
        motif = clean_image(transparent_motif_png_bytes(speckles=False), Cleanup())
        # Die Ellipse fuellt weniger als die gesamte Zuschnittflaeche.
        coverage = motif.mask.mean()
        assert 0.6 < coverage < 0.95
        assert motif.used_alpha is True
        # Die Ecken des Zuschnitts liegen ausserhalb der Ellipse.
        assert not motif.mask[0, 0]
        assert not motif.mask[-1, -1]

    def test_kleine_pixelinseln_werden_entfernt(self):
        with_speckles = add_speckles(asymmetric_motif_rgba(), count=40, seed=1)
        motif = clean_image(to_png_bytes(with_speckles), Cleanup())
        assert motif.removed_components > 0
        # Nach dem Entfernen bleibt genau eine Komponente uebrig.
        import cv2

        count, _ = cv2.connectedComponents(motif.mask.astype(np.uint8), connectivity=8)
        assert count - 1 == 1

    def test_speckles_vergroessern_den_zuschnitt_nicht(self):
        ohne = clean_image(transparent_motif_png_bytes(speckles=False), Cleanup())
        mit = clean_image(transparent_motif_png_bytes(speckles=True), Cleanup())
        assert abs(ohne.width - mit.width) <= 2
        assert abs(ohne.height - mit.height) <= 2

    def test_bild_ohne_alphakanal_ueber_hintergrundschwelle(self):
        motif = clean_image(opaque_motif_png_bytes(), Cleanup())
        assert motif.used_alpha is False
        assert motif.mask.any()

    def test_leeres_bild_wird_abgelehnt(self):
        blank = np.zeros((64, 64, 4), dtype=np.uint8)
        with pytest.raises(MotifNotFound):
            clean_image(to_png_bytes(blank), Cleanup())


class TestPlacement:
    def test_motiv_bleibt_innerhalb_der_platte(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        x0, y0, x1, y1 = raster.motif_bbox_mm
        margin = config.plate.margin_mm
        assert x0 >= margin - 0.5
        assert y0 >= margin - 0.5
        assert x1 <= config.plate.width_mm - margin + 0.5
        assert y1 <= config.plate.height_mm - margin + 0.5

    def test_seitenverhaeltnis_bleibt_erhalten(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        x0, y0, x1, y1 = raster.motif_bbox_mm
        source_ratio = motif.width / motif.height
        placed_ratio = (x1 - x0) / (y1 - y0)
        assert placed_ratio == pytest.approx(source_ratio, rel=0.02)

    def test_motiv_ist_zentriert(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        x0, y0, x1, y1 = raster.motif_bbox_mm
        assert (x0 + x1) / 2 == pytest.approx(config.plate.width_mm / 2, abs=0.5)
        assert (y0 + y1) / 2 == pytest.approx(config.plate.height_mm / 2, abs=0.5)

    def test_motiv_wird_nicht_gespiegelt(self, config: ProjectConfig):
        """Das dunkle Quadrat sitzt im Testbild oben links.

        Bildzeile 0 muss auf grosse Y-Werte abgebildet werden. Eine Spiegelung
        oder eine 180-Grad-Drehung wuerde den tiefsten Punkt in einen anderen
        Quadranten schieben.
        """
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        row, col = np.unravel_index(int(np.argmax(raster.darkness)), raster.darkness.shape)
        x_mm = float(raster.col_to_x(col))
        y_mm = float(raster.row_to_y(row))
        assert x_mm < config.plate.width_mm / 2, "dunkelste Stelle muss links liegen"
        assert y_mm > config.plate.height_mm / 2, "dunkelste Stelle muss oben liegen"

    def test_helle_stelle_liegt_unten_rechts(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        inside = raster.mask & (raster.darkness < 0.03)
        rows, cols = np.nonzero(inside)
        assert len(rows) > 0
        x_mm = float(raster.col_to_x(cols.mean()))
        y_mm = float(raster.row_to_y(rows.mean()))
        assert x_mm > config.plate.width_mm / 2
        assert y_mm < config.plate.height_mm / 2


class TestToneMapping:
    def test_tiefe_ueberschreitet_das_maximum_nie(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        assert raster.depth.min() >= -config.carving.max_depth_mm - 1e-9
        assert raster.depth.max() <= 0.0

    def test_dunkel_wird_tiefer_als_hell(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        inside = raster.mask
        dark = raster.darkness[inside] > 0.6
        light = raster.darkness[inside] < 0.2
        assert dark.any() and light.any()
        assert raster.depth[inside][dark].mean() < raster.depth[inside][light].mean()

    def test_ausserhalb_der_maske_wird_nicht_geschnitten(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        assert not raster.cut[~raster.mask].any()
        assert raster.darkness[~raster.mask].max() == 0.0

    def test_schwelle_laesst_helle_bereiche_ungeschnitten(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        below = raster.mask & (raster.darkness <= config.carving.tone_threshold)
        assert not raster.cut[below].any()

    def test_gamma_verschiebt_die_tiefenverteilung(self):
        base = ProjectConfig()
        steep = ProjectConfig.model_validate(
            {"schema_version": "1.0", "carving": {"depth_gamma": 2.5}}
        )
        motif = clean_image(transparent_motif_png_bytes(), base.cleanup)
        flat_depth = place_motif(motif, base).depth
        steep_depth = place_motif(motif, steep).depth
        # Groesseres Gamma macht mittlere Tonwerte flacher.
        assert steep_depth.mean() > flat_depth.mean()


class TestEnvelope:
    def test_dilatation_um_5_mm_wird_korrekt_umgerechnet(self):
        mask = np.zeros((200, 200), dtype=bool)
        mask[95:105, 95:105] = True
        px_per_mm = 4.0
        grown = dilate_mask_mm(mask, 5.0, px_per_mm)

        rows = np.flatnonzero(grown.any(axis=1))
        expected_growth_px = 5.0 * px_per_mm
        grown_top = 95 - rows[0]
        grown_bottom = rows[-1] - 104
        assert grown_top == pytest.approx(expected_growth_px, abs=1.5)
        assert grown_bottom == pytest.approx(expected_growth_px, abs=1.5)

    def test_dilatation_ist_richtungsunabhaengig(self):
        mask = np.zeros((200, 200), dtype=bool)
        mask[100, 100] = True
        grown = dilate_mask_mm(mask, 5.0, 4.0)
        rows = np.flatnonzero(grown.any(axis=1))
        cols = np.flatnonzero(grown.any(axis=0))
        assert (rows[-1] - rows[0]) == pytest.approx(cols[-1] - cols[0], abs=1)

    def test_null_rand_laesst_die_maske_unveraendert(self):
        mask = np.zeros((50, 50), dtype=bool)
        mask[20:30, 20:30] = True
        assert np.array_equal(dilate_mask_mm(mask, 0.0, 4.0), mask)

    def test_huelle_umschliesst_das_motiv(self, config: ProjectConfig):
        motif = clean_image(transparent_motif_png_bytes(), config.cleanup)
        raster = place_motif(motif, config)
        envelope = build_envelope(raster, config.carving.motif_margin_mm)
        assert envelope.mask.sum() > raster.mask.sum()
        assert np.all(envelope.mask[raster.mask])
        assert envelope.motif_contours_mm and envelope.envelope_contours_mm
