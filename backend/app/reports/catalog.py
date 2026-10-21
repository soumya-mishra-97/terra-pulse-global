"""Report section catalogue, groups and reporting periods (shared by API validation and UI)."""

from __future__ import annotations

from typing import Literal

SectionId = Literal[
    "executive_summary", "country_overview", "current_population", "historical_trends", "annual_change",
    "growth_rate", "birth_death", "fertility_life", "age_structure", "urban_rural", "density", "migration",
    "comparison", "projections", "key_findings", "sources_methodology",
]

SECTIONS: list[tuple[str, str]] = [
    ("executive_summary", "Executive Summary"),
    ("country_overview", "Country Overview"),
    ("current_population", "Current Population Estimate"),
    ("historical_trends", "Historical Population Trends"),
    ("annual_change", "Annual Population Change"),
    ("growth_rate", "Population Growth Rate"),
    ("birth_death", "Birth Rate and Death Rate"),
    ("fertility_life", "Fertility Rate and Life Expectancy"),
    ("age_structure", "Age Distribution and Demographic Structure"),
    ("urban_rural", "Urban vs. Rural Population"),
    ("density", "Population Density and Geographic Distribution"),
    ("migration", "Migration Trends"),
    ("comparison", "Comparison with Regional and Global Trends"),
    ("projections", "Future Population Projections"),
    ("key_findings", "Key Findings and Implications"),
    ("sources_methodology", "Data Sources, Methodology, Limitations, and Uncertainty"),
]
SECTION_TITLES = dict(SECTIONS)
SECTION_ORDER = [s for s, _ in SECTIONS]
REQUIRED_SECTIONS = ("executive_summary", "country_overview", "key_findings", "sources_methodology")

SECTION_GROUPS = {
    "population_trends": {"label": "Population trends",
                          "sections": ["current_population", "historical_trends", "annual_change", "growth_rate"]},
    "demographic_indicators": {"label": "Demographic indicators",
                               "sections": ["birth_death", "fertility_life", "age_structure", "urban_rural", "density",
                                            "migration"]},
    "research_sources": {"label": "Research and sources", "sections": ["sources_methodology"]},
    "charts_comparisons": {"label": "Charts and comparisons", "sections": ["comparison"]},
    "future_projections": {"label": "Future projections", "sections": ["projections"]},
}

PeriodKey = Literal["latest", "5y", "10y", "max"]
PERIODS = {
    "latest": {"label": "Latest available data", "years": 1},
    "5y": {"label": "Last 5 years", "years": 5},
    "10y": {"label": "Last 10 years", "years": 10},
    "max": {"label": "Since 2000 (full snapshot)", "years": None},
}
FIRST_YEAR = 2000


def normalise_sections(requested: list[str]) -> list[str]:
    chosen = set(requested) | set(REQUIRED_SECTIONS)
    return [s for s in SECTION_ORDER if s in chosen]


def period_years(key: str, latest_year: int) -> tuple[int, int]:
    years = PERIODS[key]["years"]
    start = FIRST_YEAR if years is None else max(FIRST_YEAR, latest_year - years)
    return start, latest_year


def flag_emoji(iso2: str | None) -> str:
    if not iso2 or len(iso2) != 2 or not iso2.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())
