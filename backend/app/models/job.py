"""Jobmodelle. Enthalten bewusst keine internen Dateipfade."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.config import ProjectConfig


class JobStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class PathMetrics(BaseModel):
    """Kennzahlen der berechneten Bahn."""

    line_count: int = 0
    connector_count: int = 0
    raw_point_count: int = 0
    simplified_point_count: int = 0
    reduction_percent: float = 0.0
    avg_points_per_line: float = 0.0
    max_points_per_line: int = 0
    cut_length_mm: float = 0.0
    travel_length_mm: float = 0.0
    min_z_mm: float = 0.0
    max_z_mm: float = 0.0
    longest_connector_mm: float = 0.0
    estimated_step_size_kb: float = 0.0
    groove_width_mm: float = 0.0
    remaining_thickness_mm: float = 0.0
    motif_bbox_mm: list[float] = Field(default_factory=list)
    mm_per_pixel: float = 0.0


class Artifacts(BaseModel):
    """Welche Downloads fuer den Job bereitstehen."""

    project: bool = False
    cleaned_png: bool = False
    toolpath_png: bool = False
    simulation_png: bool = False
    step: bool = False
    stl: bool = False
    report: bool = False


class Job(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued
    progress: float = 0.0
    stage: str = "queued"
    message: str = "Job angelegt."
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    config: ProjectConfig | None = None
    metrics: PathMetrics | None = None
    artifacts: Artifacts = Field(default_factory=Artifacts)
    warnings: list[str] = Field(default_factory=list)
    report_passed: bool | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()
