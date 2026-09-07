"""Modelle des technischen Pruefberichts."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.job import PathMetrics

REPORT_SCHEMA_VERSION = "1.0"


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str
    value: float | int | str | bool | list[float] | None = None
    expected: str | None = None


class ValidationReport(BaseModel):
    schema_version: str = REPORT_SCHEMA_VERSION
    job_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    mode: str = "v_cutting"
    passed: bool = False
    checks: list[CheckResult] = Field(default_factory=list)
    metrics: PathMetrics | None = None
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Diese Datei enthaelt reine Geometrie. Sie ist kein geprueftes Maschinenprogramm. "
        "Vor dem Fraesen ist eine Simulation in CATIA beziehungsweise im NC-Postprozessor "
        "zwingend erforderlich. Vorschuebe und Drehzahlen werden bewusst nicht vorgegeben."
    )

    def add(
        self,
        name: str,
        passed: bool,
        detail: str,
        value: float | int | str | bool | list[float] | None = None,
        expected: str | None = None,
    ) -> None:
        self.checks.append(
            CheckResult(name=name, passed=passed, detail=detail, value=value, expected=expected)
        )

    def finalize(self) -> ValidationReport:
        self.passed = all(check.passed for check in self.checks)
        return self
