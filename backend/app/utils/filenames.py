"""Sichere Dateinamen und Jobkennungen.

Nutzereingaben duerfen niemals ungeprueft in Pfade fliessen.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MULTI_DOT = re.compile(r"\.{2,}")

MAX_SLUG_LENGTH = 64


def safe_slug(value: str, fallback: str = "projekt") -> str:
    """Reduziert einen beliebigen String auf sichere Dateinamenzeichen."""
    cleaned = _UNSAFE.sub("-", (value or "").strip())
    cleaned = _MULTI_DOT.sub(".", cleaned).strip("-._")
    cleaned = cleaned[:MAX_SLUG_LENGTH]
    return cleaned or fallback


def safe_job_id(value: str) -> str:
    """Akzeptiert ausschliesslich gueltige UUIDs.

    Damit ist jede Form von Pfadmanipulation ueber die Job-ID ausgeschlossen.
    """
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Ungueltige Job-ID: {value!r}") from exc


def upload_suffix(filename: str | None, content_format: str | None) -> str:
    """Ermittelt eine sichere Dateiendung fuer den Upload.

    Der vom Browser gemeldete Name wird nur als Hinweis genutzt; massgeblich
    ist das von Pillow erkannte Bildformat.
    """
    by_format = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
    if content_format and content_format.upper() in by_format:
        return by_format[content_format.upper()]
    suffix = Path(safe_slug(filename or "")).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".png"


def ensure_within(base: Path, candidate: Path) -> Path:
    """Stellt sicher, dass candidate unterhalb von base liegt."""
    base_resolved = base.resolve()
    candidate_resolved = candidate.resolve()
    if base_resolved != candidate_resolved and base_resolved not in candidate_resolved.parents:
        raise ValueError(f"Pfad {candidate} liegt ausserhalb von {base}.")
    return candidate_resolved
