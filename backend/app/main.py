"""FastAPI-Anwendung des Image-to-V-Cutting-Backends."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health, jobs
from app.api.deps import get_store
from app.settings import CORS_ORIGINS, JOB_RETENTION_SECONDS, ensure_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Wandelt hochgeladene Bilder in CATIA-kompatible V-Carving-Bahnen um.

Die erzeugte STEP-Datei enthaelt reine Geometrie. Sie ist **kein** geprueftes
Maschinenprogramm. Vor dem Fraesen ist eine Simulation in CATIA
beziehungsweise im NC-Postprozessor zwingend erforderlich.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    removed = get_store().cleanup_expired(JOB_RETENTION_SECONDS)
    if removed:
        logger.info("%d abgelaufene Jobverzeichnisse entfernt.", removed)
    yield


app = FastAPI(
    title="Image to V-Cutting",
    version="0.1.0",
    description=DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(jobs.config_router, prefix="/api")


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "static"


# Im Produktions-Container liegen Frontend und API auf derselben Adresse.
# Lokal bleibt der Vite-Entwicklungsserver weiterhin moeglich.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": "Image to V-Cutting",
            "docs": "/docs",
            "health": "/api/health",
        }
