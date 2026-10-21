from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.reports.catalog import PeriodKey, SectionId

ISO3 = re.compile(r"^[A-Z]{3}$")


class GenerateReportRequest(BaseModel):
    country_code: str = Field(min_length=3, max_length=3, description="ISO 3166-1 alpha-3 code")
    period: PeriodKey = "10y"
    sections: list[SectionId] = Field(default_factory=list, max_length=16)

    @field_validator("country_code")
    @classmethod
    def upper_iso3(cls, v: str) -> str:
        v = v.strip().upper()
        if not ISO3.match(v):
            raise ValueError("country_code must be a 3-letter ISO code")
        return v


class ReportCountry(BaseModel):
    iso3: str
    iso2: str | None
    name: str
    region: str | None
    income_level: str | None
    flag: str
    latest_population_year: int | None


class ReportSummary(BaseModel):
    id: str
    country_code: str
    country_name: str
    period: str
    sections: list[str]
    status: Literal["queued", "running", "completed", "failed", "blocked"]
    progress: int
    current_step: str | None
    error: str | None
    validation_status: str | None
    mode: str | None
    created_at: datetime
    generated_at: datetime | None
    downloads: dict[str, str]


class ReportDetail(ReportSummary):
    content: dict | None
    sources: list[dict]
    runs: list[dict]


class ReportPage(BaseModel):
    items: list[ReportSummary]
    total: int
    limit: int
    offset: int


class ReportOptions(BaseModel):
    sections: list[dict]
    groups: dict
    periods: dict
    required: list[str]
