from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Freshness(BaseModel):
    status: str
    age_days: int | None
    stale_after_days: int


class Provenance(BaseModel):
    source_id: int
    snapshot_id: str
    dataset_name: str
    publisher: str
    source_url: str
    landing_page: str | None
    license: str
    release_version: str
    imported_at: datetime
    reference_date: date | None
    value_kind: str
    uncertainty_note: str
    freshness: Freshness
    is_synthetic: bool
    data_label: str = Field(description="Human-readable label shown next to every figure")


class Estimate(BaseModel):
    value: float
    reference_date: date
    value_kind: str
    method: str
    lower: float | None = None
    upper: float | None = None
    uncertainty_note: str


class IllustrativeCounter(BaseModel):
    label: str = "Illustrative projection - not an official figure"
    base_value: float
    base_date: date
    annual_growth_percent: float
    value_kind: str = "illustrative_projection"
    assumptions: list[str]


class YearValue(BaseModel):
    year: int
    value: float


class RankedCountry(BaseModel):
    iso3: str
    name: str
    value: float
    year: int


class WorldSummary(BaseModel):
    estimate: Estimate
    previous: YearValue | None
    annual_change: float | None
    annual_change_percent: float | None
    growth_rate_percent: YearValue | None
    history: list[YearValue]
    top_countries: list[RankedCountry]
    fastest_growing: list[RankedCountry]
    country_count: int
    coverage: dict
    illustrative_counter: IllustrativeCounter | None
    provenance: Provenance


class CountryListItem(BaseModel):
    iso3: str
    iso2: str | None
    name: str
    region: str | None
    region_code: str | None
    income_level: str | None
    capital: str | None
    population: float | None
    population_year: int | None
    growth_percent: float | None
    growth_year: int | None
    share_of_world_percent: float | None


class CountryPage(BaseModel):
    items: list[CountryListItem]
    total: int
    limit: int
    offset: int
    provenance: Provenance


class CitySource(BaseModel):
    snapshot_id: str
    dataset_name: str
    publisher: str
    source_url: str
    landing_page: str | None
    license: str
    retrieved_at: datetime
    value_kind: str
    reference_date_convention: str


class CityOut(BaseModel):
    geonameid: int
    name: str
    admin1: str | None
    country_iso2: str
    country_iso3: str | None
    country_name: str | None
    population: int
    record_modified: date = Field(description="When the source last edited the record, not the population reference date")


class CityPage(BaseModel):
    items: list[CityOut]
    total: int
    source: CitySource


class ChangeOut(BaseModel):
    start_year: int
    end_year: int
    absolute: float
    percent: float
    cagr_percent: float | None


class HistoryPoint(BaseModel):
    year: int
    value: float
    reference_date: date


class HistoryResponse(BaseModel):
    iso3: str
    name: str
    metric: str
    unit: str
    value_kind: str
    points: list[HistoryPoint]
    change: ChangeOut | None
    provenance: Provenance


class RegionStat(BaseModel):
    code: str
    name: str
    year: int | None
    population: float | None
    growth_percent: float | None
    age_0_14_pct: float | None
    age_15_64_pct: float | None
    age_65_plus_pct: float | None
    urban_pct: float | None
    fertility_rate: float | None
    life_expectancy_years: float | None


class RegionsResponse(BaseModel):
    regions: list[RegionStat]
    world: RegionStat | None
    provenance: Provenance


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    snapshot_id: str
    dataset_name: str
    publisher: str
    release_version: str
    license: str
    imported_at: datetime
    is_active: bool
    is_synthetic: bool
    checksum: str
