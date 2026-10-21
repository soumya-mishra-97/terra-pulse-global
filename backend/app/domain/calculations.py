"""Deterministic demographic arithmetic.

These functions are the *only* place TerraPulse computes numbers. LLM output never feeds
back into them, and they never import FastAPI, SQLAlchemy or LangChain.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.domain.errors import CalculationError
from app.domain.models import ValueKind

Series = Mapping[int, float]  # year -> value


@dataclass(frozen=True)
class Change:
    start_year: int
    end_year: int
    start_value: float
    end_value: float
    absolute: float
    percent: float
    cagr_percent: float | None


@dataclass(frozen=True)
class IllustrativeProjection:
    value: float
    base_value: float
    base_date: date
    at: date
    annual_growth_percent: float
    value_kind: ValueKind
    assumptions: tuple[str, ...]


def _require_positive(value: float, label: str) -> None:
    if value is None or not math.isfinite(value) or value <= 0:
        raise CalculationError(f"{label} must be a positive finite number, got {value!r}")


def absolute_change(start: float, end: float) -> float:
    return end - start


def percent_change(start: float, end: float) -> float:
    _require_positive(start, "start value")
    return (end - start) / start * 100.0


def cagr_percent(start: float, end: float, years: int) -> float:
    """Compound annual growth rate in percent."""
    if years <= 0:
        raise CalculationError("CAGR needs a period of at least one year")
    _require_positive(start, "start value")
    _require_positive(end, "end value")
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def change_over_period(series: Series, start_year: int | None = None, end_year: int | None = None) -> Change:
    """Change between the first and last available years inside [start_year, end_year]."""
    years = sorted(y for y in series if (start_year is None or y >= start_year) and (end_year is None or y <= end_year))
    if len(years) < 2:
        raise CalculationError("at least two observations are required to compute a change")
    y0, y1 = years[0], years[-1]
    v0, v1 = float(series[y0]), float(series[y1])
    span = y1 - y0
    return Change(
        start_year=y0,
        end_year=y1,
        start_value=v0,
        end_value=v1,
        absolute=absolute_change(v0, v1),
        percent=percent_change(v0, v1),
        cagr_percent=cagr_percent(v0, v1, span) if v0 > 0 and v1 > 0 else None,
    )


def annual_changes(series: Series) -> list[dict]:
    """Year-over-year absolute and percent change for consecutive years only."""
    out = []
    years = sorted(series)
    for prev, cur in zip(years, years[1:], strict=False):
        if cur - prev != 1:
            continue  # gap in data: do not silently interpolate
        v0, v1 = float(series[prev]), float(series[cur])
        out.append(
            {
                "year": cur,
                "absolute": v1 - v0,
                "percent": percent_change(v0, v1) if v0 > 0 else None,
            }
        )
    return out


def share_percent(part: float, whole: float) -> float:
    _require_positive(whole, "whole")
    return part / whole * 100.0


def natural_increase_per_1000(birth_rate: float, death_rate: float) -> float:
    return birth_rate - death_rate


def dependency_ratio(age_0_14_pct: float, age_15_64_pct: float, age_65_plus_pct: float) -> float:
    """Dependants (0-14 and 65+) per 100 working-age people (15-64)."""
    _require_positive(age_15_64_pct, "working-age share")
    return (age_0_14_pct + age_65_plus_pct) / age_15_64_pct * 100.0


def rank_desc(values: Mapping[str, float]) -> list[tuple[str, float]]:
    """Sort keys by value descending; ties broken by key for determinism."""
    return sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))


def check_comparable_years(series_by_key: Mapping[str, Series], start_year: int, end_year: int) -> list[str]:
    """Return keys that lack observations for both comparison endpoints."""
    return [k for k, s in series_by_key.items() if start_year not in s or end_year not in s]


def illustrative_projection(base_value: float, base_date: date, annual_growth_percent: float, at: date) -> IllustrativeProjection:
    """Continuous-compounding extrapolation used ONLY for the animated counter.

    This is not an official estimate. It assumes the source's latest annual growth rate holds
    constant from the reference date, which real populations do not do.
    """
    _require_positive(base_value, "base value")
    if not math.isfinite(annual_growth_percent) or abs(annual_growth_percent) > 10:
        raise CalculationError("annual growth rate outside plausible bounds (|r| <= 10%)")
    years = (at - base_date).days / 365.2425
    # WDI SP.POP.GROW is an exponential rate: P(t) = P(t-1) * exp(r/100).
    value = base_value * math.exp(annual_growth_percent / 100.0 * years)
    return IllustrativeProjection(
        value=value,
        base_value=base_value,
        base_date=base_date,
        at=at,
        annual_growth_percent=annual_growth_percent,
        value_kind=ValueKind.ILLUSTRATIVE_PROJECTION,
        assumptions=(
            f"Starts from the source estimate for {base_date.isoformat()}.",
            f"Applies the source's latest annual exponential growth rate ({annual_growth_percent:.3f}%) continuously.",
            "Ignores seasonality, shocks and revisions; it is not an official figure.",
        ),
    )


def series_bounds(series: Sequence[tuple[int, float]]) -> tuple[int, int] | None:
    if not series:
        return None
    years = [y for y, _ in series]
    return min(years), max(years)
