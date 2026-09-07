"""Validierung hochgeladener Bilder.

Der gemeldete MIME-Type wird bewusst ignoriert. Massgeblich ist ausschliesslich
der tatsaechliche Dateiinhalt, wie Pillow ihn liest.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
"""20 MB, wie in der Oberflaeche angekuendigt."""

MAX_PIXELS = 40_000_000
"""Obergrenze der dekomprimierten Bildflaeche gegen Dekompressionsbomben."""

MAX_EDGE_PIXELS = 12_000
"""Obergrenze je Kantenlaenge."""

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}

# Pillow soll selbst warnen statt still riesige Bilder zu dekodieren.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class UploadRejected(ValueError):
    """Der Upload ist unbrauchbar oder unsicher."""


@dataclass(frozen=True)
class UploadInfo:
    image_format: str
    width: int
    height: int
    has_alpha: bool
    size_bytes: int


def validate_image_bytes(data: bytes) -> UploadInfo:
    """Prueft Groesse, Format und Lesbarkeit eines Uploads.

    Wirft :class:`UploadRejected` mit einer verstaendlichen Meldung, sobald
    etwas nicht stimmt. Es wird zweimal geoeffnet: einmal fuer ``verify()``
    (erkennt abgeschnittene Dateien) und einmal fuer den echten Ladevorgang,
    weil ``verify()`` das Objekt unbrauchbar macht.
    """
    if not data:
        raise UploadRejected("Die hochgeladene Datei ist leer.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            f"Die Datei ist {len(data) / 1024 / 1024:.1f} MB gross. "
            f"Erlaubt sind hoechstens {MAX_UPLOAD_BYTES // 1024 // 1024} MB."
        )

    try:
        with Image.open(io.BytesIO(data)) as probe:
            image_format = (probe.format or "").upper()
            width, height = probe.size
            probe.verify()
    except UnidentifiedImageError as exc:
        raise UploadRejected(
            "Der Dateiinhalt ist kein lesbares Bild. Erlaubt sind PNG, JPG und WebP."
        ) from exc
    except Image.DecompressionBombError as exc:
        raise UploadRejected("Das Bild ist nach dem Entpacken zu gross.") from exc
    except OSError as exc:
        raise UploadRejected(f"Das Bild ist beschaedigt oder unvollstaendig: {exc}") from exc

    if image_format not in ALLOWED_FORMATS:
        raise UploadRejected(
            f"Format {image_format or 'unbekannt'} wird nicht unterstuetzt. Erlaubt sind PNG, JPG und WebP."
        )
    if width <= 0 or height <= 0:
        raise UploadRejected("Das Bild hat keine gueltigen Abmessungen.")
    if width > MAX_EDGE_PIXELS or height > MAX_EDGE_PIXELS:
        raise UploadRejected(
            f"Das Bild ist {width}x{height} Pixel gross. "
            f"Erlaubt sind hoechstens {MAX_EDGE_PIXELS} Pixel je Kante."
        )
    if width * height > MAX_PIXELS:
        raise UploadRejected(
            f"Das Bild hat {width * height} Pixel. Erlaubt sind hoechstens {MAX_PIXELS} Pixel."
        )

    # Zweiter Durchlauf: erzwingt vollstaendiges Dekodieren.
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            has_alpha = img.mode in {"RGBA", "LA", "PA"} or "transparency" in img.info
    except Image.DecompressionBombError as exc:
        raise UploadRejected("Das Bild ist nach dem Entpacken zu gross.") from exc
    except OSError as exc:
        raise UploadRejected(f"Das Bild konnte nicht vollstaendig gelesen werden: {exc}") from exc

    return UploadInfo(
        image_format=image_format,
        width=width,
        height=height,
        has_alpha=bool(has_alpha),
        size_bytes=len(data),
    )
