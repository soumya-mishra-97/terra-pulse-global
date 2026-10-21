"""Framework-free domain models. No FastAPI, SQLAlchemy or LLM imports allowed in app.domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class ValueKind(StrEnum):
    """How a number was produced. Every figure the API returns carries one of these."""

    OBSERVED_COUNT = "observed_count"  # e.g. a census enumeration
    ESTIMATE = "estimate"  # modelled value for a past/current date published by a source
    PROJECTION = "projection"  # official forward-looking scenario published by a source
    DERIVED = "derived"  # deterministic arithmetic over source values (growth, ratios)
    ILLUSTRATIVE_PROJECTION = "illustrative_projection"  # TerraPulse extrapolation for display only


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Country:
    iso3: str
    name: str
    iso2: str | None = None
    region_code: str | None = None
    region: str | None = None
    income_level: str | None = None
    capital: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_aggregate: bool = False


@dataclass(frozen=True)
class DataSource:
    id: int
    snapshot_id: str
    dataset_name: str
    publisher: str
    source_url: str
    license: str
    release_version: str
    imported_at: datetime
    checksum: str
    geographic_coverage: str
    methodology_notes: str
    uncertainty_note: str
    reference_date_convention: str
    is_active: bool = True
    is_synthetic: bool = False
    landing_page: str | None = None


@dataclass(frozen=True)
class PopulationBaseline:
    """One source observation: (country, metric, year) -> value."""

    country_iso3: str
    metric: str
    unit: str
    year: int
    value: float
    value_kind: ValueKind = ValueKind.ESTIMATE

    @property
    def reference_date(self) -> date:
        return reference_date_for_year(self.year)


@dataclass(frozen=True)
class PopulationEstimate:
    scope: str  # "WLD" or ISO3
    value: float
    reference_date: date
    value_kind: ValueKind
    source_id: int
    method: str
    lower: float | None = None
    upper: float | None = None
    uncertainty_note: str = "Uncertainty not quantified by the source."


@dataclass(frozen=True)
class SourceEvent:
    event_type: str
    details: dict = field(default_factory=dict)
    source_id: int | None = None


@dataclass
class CalculationRun:
    kind: str
    params: dict
    inputs_hash: str
    status: str = "pending"
    output_summary: dict = field(default_factory=dict)


def reference_date_for_year(year: int) -> date:
    """WDI annual population figures are midyear (1 July) estimates."""
    return date(year, 7, 1)
