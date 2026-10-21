"""Deterministic display formatting shared by API, agents, Markdown and PDF output."""

from __future__ import annotations


def fmt_people(value: float | None) -> str:
    if value is None:
        return "Data unavailable"
    v = abs(value)
    sign = "-" if value < 0 else ""
    if v >= 1e9:
        return f"{sign}{v / 1e9:.2f} billion"
    if v >= 1e6:
        return f"{sign}{v / 1e6:.1f} million"
    if v >= 1e4:
        return f"{sign}{v:,.0f}"
    return f"{sign}{v:,.0f}"


def fmt_exact(value: float | None) -> str:
    return "Data unavailable" if value is None else f"{value:,.0f}"


def fmt_pct(value: float | None, digits: int = 2, signed: bool = False) -> str:
    if value is None:
        return "Data unavailable"
    return f"{value:+.{digits}f}%" if signed else f"{value:.{digits}f}%"


def fmt_num(value: float | None, digits: int = 1, unit: str = "") -> str:
    if value is None:
        return "Data unavailable"
    s = f"{value:,.{digits}f}"
    return f"{s} {unit}".strip()


def fmt_metric(metric: str, value: float | None) -> str:
    if value is None:
        return "Data unavailable"
    if metric in ("population_total",):
        return fmt_people(value)
    if metric == "net_migration":
        return f"{value:+,.0f} people"
    if metric.endswith("_pct") or metric == "population_growth_pct":
        return fmt_pct(value, 2 if metric == "population_growth_pct" else 1)
    if metric in ("birth_rate_per_1000", "death_rate_per_1000"):
        return f"{value:.1f} per 1,000"
    if metric == "fertility_rate":
        return f"{value:.2f} births per woman"
    if metric == "life_expectancy_years":
        return f"{value:.1f} years"
    if metric == "density_per_km2":
        return f"{value:,.1f} people per km²"
    if metric == "land_area_km2":
        return f"{value:,.0f} km²"
    return f"{value:,.2f}"


METRIC_LABELS = {
    "population_total": "Total population",
    "population_growth_pct": "Population growth rate",
    "birth_rate_per_1000": "Crude birth rate",
    "death_rate_per_1000": "Crude death rate",
    "fertility_rate": "Total fertility rate",
    "life_expectancy_years": "Life expectancy at birth",
    "age_0_14_pct": "Population aged 0-14",
    "age_15_64_pct": "Population aged 15-64",
    "age_65_plus_pct": "Population aged 65+",
    "urban_pct": "Urban population",
    "rural_pct": "Rural population",
    "density_per_km2": "Population density",
    "land_area_km2": "Land area",
    "net_migration": "Net migration",
}
