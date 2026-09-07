"""Gesundheitsendpunkt."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.config import SCHEMA_VERSION
from app.utils.validation import ALLOWED_FORMATS, MAX_PIXELS, MAX_UPLOAD_BYTES

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    schema_version: str
    max_upload_bytes: int
    max_pixels: int
    allowed_formats: list[str]
    occ_available: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        import OCP  # noqa: F401

        occ_available = True
    except ImportError:
        occ_available = False

    return HealthResponse(
        status="ok",
        schema_version=SCHEMA_VERSION,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        max_pixels=MAX_PIXELS,
        allowed_formats=sorted(ALLOWED_FORMATS),
        occ_available=occ_available,
    )
