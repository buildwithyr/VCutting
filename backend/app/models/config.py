"""Pydantic-Modelle des versionierten Projektformats.

Das JSON-Schema unter shared/schemas/vcutting-project-1.0.schema.json ist die
normative Beschreibung, diese Modelle sind die serverseitige Durchsetzung.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"

SimplificationMode = Literal["catia_strong", "catia_normal", "fine"]
Orientation = Literal["vertical", "horizontal"]
ProcessingMode = Literal["v_cutting", "relief"]

#: Voreinstellungen der Vereinfachungsstufen (Abschnitt 3/7 der Spezifikation).
SIMPLIFICATION_PRESETS: dict[str, dict[str, float]] = {
    "catia_strong": {
        "sample_distance_mm": 2.0,
        "smoothing_distance_mm": 2.0,
        "rdp_tolerance_mm": 0.18,
        "target_reduction_percent": 90.0,
    },
    "catia_normal": {
        "sample_distance_mm": 1.0,
        "smoothing_distance_mm": 1.0,
        "rdp_tolerance_mm": 0.08,
        "target_reduction_percent": 80.0,
    },
    "fine": {
        "sample_distance_mm": 0.5,
        "smoothing_distance_mm": 0.3,
        "rdp_tolerance_mm": 0.03,
        "target_reduction_percent": 50.0,
    },
}

#: Ab dieser Reduktion gilt der Export als CATIA-freundlich.
MIN_ACCEPTABLE_REDUCTION_PERCENT = 85.0


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectMeta(StrictModel):
    name: str = Field(default="V-Cutting Projekt", min_length=1, max_length=120)
    created_at: str | None = None

    @model_validator(mode="after")
    def _fill_timestamp(self) -> ProjectMeta:
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        return self


class Plate(StrictModel):
    width_mm: float = Field(default=400.0, gt=0, le=2000)
    height_mm: float = Field(default=400.0, gt=0, le=2000)
    thickness_mm: float = Field(default=3.0, gt=0, le=200)
    top_z_mm: float = 0.0
    margin_mm: float = Field(default=20.0, ge=0, le=500)

    @model_validator(mode="after")
    def _margin_fits(self) -> Plate:
        if 2 * self.margin_mm >= min(self.width_mm, self.height_mm):
            raise ValueError(
                "Plattenrand ist zu gross: 2 x margin_mm muss kleiner als die kleinere Plattenseite sein."
            )
        return self


class Tool(StrictModel):
    id: str = Field(default="T246", min_length=1, max_length=32)
    name: str = Field(default="V-Nutfraeser", min_length=1, max_length=80)
    type: Literal["v_bit"] = "v_bit"
    angle_deg: float = Field(default=90.0, gt=0, lt=180)


class Carving(StrictModel):
    max_depth_mm: float = Field(default=1.2, gt=0, le=100)
    line_spacing_mm: float = Field(default=2.0, gt=0, le=100)
    orientation: Orientation = "vertical"
    path_mode: Literal["serpentine"] = "serpentine"
    clearance_z_mm: float = Field(default=1.0, gt=0, le=100)
    motif_margin_mm: float = Field(default=5.0, ge=0, le=200)
    tone_threshold: float = Field(default=0.055, ge=0, le=1)
    depth_gamma: float = Field(default=1.0, gt=0, le=10)


class Cleanup(StrictModel):
    remove_speckles: bool = True
    keep_largest_component: bool = True
    smooth_raster_edges: bool = True
    transparent_background: bool = True
    background_threshold: float = Field(default=0.95, ge=0, le=1)
    min_component_area_ratio: float = Field(default=0.0005, ge=0, le=0.5)


class Simplification(StrictModel):
    mode: SimplificationMode = "catia_strong"
    sample_distance_mm: float | None = Field(default=None, gt=0, le=50)
    smoothing_distance_mm: float | None = Field(default=None, ge=0, le=50)
    rdp_tolerance_mm: float | None = Field(default=None, gt=0, le=10)
    target_reduction_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _apply_preset(self) -> Simplification:
        preset = SIMPLIFICATION_PRESETS[self.mode]
        for key, value in preset.items():
            if getattr(self, key) is None:
                setattr(self, key, value)
        return self

    # Nach der Validierung sind die Werte garantiert gesetzt. Diese Properties
    # ersparen dem Rest des Codes staendige None-Pruefungen.
    @property
    def sample_distance(self) -> float:
        assert self.sample_distance_mm is not None
        return self.sample_distance_mm

    @property
    def smoothing_distance(self) -> float:
        assert self.smoothing_distance_mm is not None
        return self.smoothing_distance_mm

    @property
    def rdp_tolerance(self) -> float:
        assert self.rdp_tolerance_mm is not None
        return self.rdp_tolerance_mm

    @property
    def target_reduction(self) -> float:
        assert self.target_reduction_percent is not None
        return self.target_reduction_percent


class Relief(StrictModel):
    height_mm: float = Field(default=2.0, gt=0, le=200)
    invert: bool = False
    smoothing_mm: float = Field(default=0.5, ge=0, le=50)
    base_thickness_mm: float = Field(default=1.0, gt=0, le=200)
    sample_distance_mm: float = Field(default=0.5, gt=0, le=10)


class Output(StrictModel):
    include_reference_plate: bool = True
    step: bool = True
    stl: bool = False
    preview_png: bool = True


class ProjectConfig(StrictModel):
    schema_version: str = SCHEMA_VERSION
    mode: ProcessingMode = "v_cutting"
    project: ProjectMeta = Field(default_factory=ProjectMeta)
    plate: Plate = Field(default_factory=Plate)
    tool: Tool = Field(default_factory=Tool)
    carving: Carving = Field(default_factory=Carving)
    cleanup: Cleanup = Field(default_factory=Cleanup)
    simplification: Simplification = Field(default_factory=Simplification)
    relief: Relief = Field(default_factory=Relief)
    output: Output = Field(default_factory=Output)

    @model_validator(mode="after")
    def _cross_field_rules(self) -> ProjectConfig:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Nicht unterstuetzte schema_version {self.schema_version!r}. "
                f"Erwartet wird {SCHEMA_VERSION!r} - bitte migrate_project_dict() verwenden."
            )

        if self.mode == "v_cutting" and self.carving.max_depth_mm >= self.plate.thickness_mm:
            raise ValueError(
                "max_depth_mm muss kleiner als thickness_mm sein, sonst wird die Platte durchtrennt."
            )

        if self.mode == "relief":
            total = self.relief.base_thickness_mm + self.relief.height_mm
            if total > self.plate.thickness_mm + 1e-9:
                raise ValueError(
                    "base_thickness_mm + height_mm darf die Plattenstaerke nicht ueberschreiten "
                    f"({total:.3f} mm > {self.plate.thickness_mm:.3f} mm)."
                )
        return self

    # -- Abgeleitete Kennwerte, die auch die Oberflaeche anzeigt ------------
    @property
    def groove_width_mm(self) -> float:
        """Nutbreite an der Oberflaeche bei maximaler Frästiefe."""
        return 2.0 * self.carving.max_depth_mm * math.tan(math.radians(self.tool.angle_deg) / 2.0)

    @property
    def remaining_thickness_mm(self) -> float:
        return self.plate.thickness_mm - self.carving.max_depth_mm

    def warnings(self) -> list[str]:
        """Nicht blockierende Hinweise fuer Oberflaeche und Prüfbericht."""
        out: list[str] = []
        if self.remaining_thickness_mm < 0.5:
            out.append(
                f"Reststaerke betraegt nur {self.remaining_thickness_mm:.2f} mm. "
                "Die Platte kann brechen oder durchscheinen."
            )
        if self.groove_width_mm > self.carving.line_spacing_mm:
            out.append(
                f"Nutbreite {self.groove_width_mm:.2f} mm ist groesser als der Linienabstand "
                f"{self.carving.line_spacing_mm:.2f} mm. Die Nuten ueberschneiden sich stark."
            )
        if self.simplification.mode == "fine":
            out.append(
                "Vereinfachungsstufe 'fine' erzeugt sehr viele Stuetzpunkte. "
                "Aeltere CATIA-STEP-Uebersetzer koennen dabei sehr langsam werden."
            )
        if self.carving.orientation == "horizontal":
            out.append("Horizontale Bahnrichtung ist gewaehlt, die Linien laufen entlang X.")
        return out


def migrate_project_dict(data: dict) -> dict:
    """Hebt aeltere Projektdateien auf die aktuelle Schemaversion.

    Aktuell existiert nur Version 1.0. Die Funktion ist der vorbereitete
    Einstiegspunkt, damit spaetere Versionen nicht ueber die Modelle
    verstreut werden muessen.
    """
    if not isinstance(data, dict):
        raise ValueError("Projektdatei muss ein JSON-Objekt sein.")

    version = str(data.get("schema_version", "")).strip()
    if not version:
        # Ohne Angabe nehmen wir die aelteste bekannte Version an.
        data = {**data, "schema_version": SCHEMA_VERSION}
        version = SCHEMA_VERSION

    if version == SCHEMA_VERSION:
        return data

    raise ValueError(
        f"Projektdatei mit schema_version {version!r} kann nicht migriert werden. "
        f"Diese Version kennt nur {SCHEMA_VERSION!r}."
    )
