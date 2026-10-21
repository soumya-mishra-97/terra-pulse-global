"""Row-level validation, coverage and freshness rules for imported demographic data."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app.domain.models import FreshnessStatus, PopulationBaseline, reference_date_for_year

ISO3_RE = re.compile(r"^[A-Z0-9]{3}$")
YEAR_RE = re.compile(r"^\d{4}$")

# Metrics that are counts of people must be non-negative integers-ish.
COUNT_METRICS = {"population_total"}
PERCENT_METRICS = {"age_0_14_pct", "age_15_64_pct", "age_65_plus_pct", "urban_pct", "rural_pct"}
POPULATION_MAX = 20_000_000_000  # sanity bound well above any plausible total


@dataclass
class RowValidationResult:
    accepted: list[PopulationBaseline] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def parse_year(raw: str) -> int:
    """Accept only 4-digit calendar years (WDI annual data). Anything else is unsupported."""
    raw = (raw or "").strip()
    if not YEAR_RE.match(raw):
        raise ValueError(f"unsupported date format {raw!r}; expected YYYY")
    year = int(raw)
    if not 1950 <= year <= 2100:
        raise ValueError(f"year {year} outside supported range 1950-2100")
    return year


def validate_rows(rows: Iterable[dict], known_countries: set[str], known_metrics: dict[str, str]) -> RowValidationResult:
    """Validate raw snapshot rows. Never coerces bad values; rejects with a reason instead."""
    result = RowValidationResult()
    seen: set[tuple[str, str, int]] = set()
    for line_no, row in enumerate(rows, start=2):  # header is line 1
        iso3 = (row.get("country_iso3") or "").strip().upper()
        metric = (row.get("metric") or "").strip()
        reason = None
        year = None
        value = None
        if not iso3:
            reason = "missing country code"
        elif not ISO3_RE.match(iso3):
            reason = f"invalid country code {iso3!r}"
        elif iso3 not in known_countries:
            reason = f"unknown country code {iso3!r}"
        elif metric not in known_metrics:
            reason = f"unsupported metric {metric!r}"
        if reason is None:
            try:
                year = parse_year(str(row.get("year", "")))
            except ValueError as exc:
                reason = str(exc)
        if reason is None:
            try:
                value = float(row.get("value", ""))
                if not math.isfinite(value):
                    raise ValueError
            except (TypeError, ValueError):
                reason = f"non-numeric value {row.get('value')!r}"
        if reason is None:
            reason = _value_rule(metric, value)
        if reason is None:
            key = (iso3, metric, year)
            if key in seen:
                reason = "duplicate row for country/metric/year"
            seen.add(key)
        if reason:
            result.rejected.append({"line": line_no, "reason": reason, "row": dict(row)})
            continue
        result.accepted.append(
            PopulationBaseline(country_iso3=iso3, metric=metric, unit=known_metrics[metric], year=year, value=value)
        )
    return result


def _value_rule(metric: str, value: float) -> str | None:
    if metric in COUNT_METRICS:
        if value <= 0:
            return "population must be positive"
        if value > POPULATION_MAX:
            return "population exceeds plausibility bound"
        if abs(value - round(value)) > 1e-6:
            return "population must be a whole number of persons"
    if metric in PERCENT_METRICS and not 0 <= value <= 100:
        return "percentage outside 0-100"
    if metric in {"birth_rate_per_1000", "death_rate_per_1000"} and not 0 <= value <= 100:
        return "rate per 1,000 outside 0-100"
    if metric == "fertility_rate" and not 0 <= value <= 15:
        return "fertility rate outside 0-15"
    if metric == "life_expectancy_years" and not 0 < value <= 120:
        return "life expectancy outside 0-120"
    if metric in {"land_area_km2", "density_per_km2"} and value < 0:
        return "area/density must be non-negative"
    return None


def coverage_report(accepted: Iterable[PopulationBaseline], expected_countries: set[str], metric: str = "population_total") -> dict:
    present = {b.country_iso3 for b in accepted if b.metric == metric}
    missing = sorted(expected_countries - present)
    total = len(expected_countries) or 1
    return {
        "metric": metric,
        "expected": len(expected_countries),
        "present": len(present & expected_countries),
        "coverage_ratio": round(len(present & expected_countries) / total, 4),
        "missing": missing,
        "complete": not missing,
    }


def assess_freshness(latest_year: int | None, today: date, stale_after_days: int) -> dict:
    if latest_year is None:
        return {"status": FreshnessStatus.UNKNOWN, "age_days": None, "reference_date": None}
    ref = reference_date_for_year(latest_year)
    age = (today - ref).days
    return {
        "status": FreshnessStatus.STALE if age > stale_after_days else FreshnessStatus.FRESH,
        "age_days": age,
        "reference_date": ref,
        "stale_after_days": stale_after_days,
    }
