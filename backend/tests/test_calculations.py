import math
from datetime import date

import pytest

from app.domain import calculations as calc
from app.domain.errors import CalculationError
from app.domain.formatting import fmt_pct, fmt_people
from app.domain.models import ValueKind


def test_percent_and_absolute_change():
    assert calc.absolute_change(100, 110) == 10
    assert calc.percent_change(100, 110) == pytest.approx(10.0)


def test_percent_change_rejects_zero_base():
    with pytest.raises(CalculationError):
        calc.percent_change(0, 10)


def test_cagr_matches_closed_form():
    assert calc.cagr_percent(100, 121, 2) == pytest.approx(10.0)


@pytest.mark.parametrize("years", [0, -1])
def test_cagr_requires_positive_period(years):
    with pytest.raises(CalculationError):
        calc.cagr_percent(100, 110, years)


def test_change_over_period_uses_first_and_last_in_window():
    s = {2010: 100.0, 2015: 110.0, 2020: 121.0, 2025: 150.0}
    ch = calc.change_over_period(s, 2010, 2020)
    assert (ch.start_year, ch.end_year, ch.absolute) == (2010, 2020, 21.0)
    assert ch.cagr_percent == pytest.approx(((121 / 100) ** 0.1 - 1) * 100)


def test_change_over_period_needs_two_points():
    with pytest.raises(CalculationError):
        calc.change_over_period({2020: 1.0})


def test_annual_changes_skip_gaps_instead_of_interpolating():
    out = calc.annual_changes({2018: 100.0, 2019: 102.0, 2021: 106.0})
    assert [r["year"] for r in out] == [2019]
    assert out[0]["absolute"] == 2.0


def test_dependency_ratio_and_natural_increase():
    assert calc.dependency_ratio(30, 60, 10) == pytest.approx(66.6667, rel=1e-4)
    assert calc.natural_increase_per_1000(20.5, 7.5) == pytest.approx(13.0)
    with pytest.raises(CalculationError):
        calc.dependency_ratio(30, 0, 10)


def test_rank_is_deterministic_on_ties():
    assert calc.rank_desc({"BBB": 1.0, "AAA": 1.0, "CCC": 2.0}) == [("CCC", 2.0), ("AAA", 1.0), ("BBB", 1.0)]


def test_check_comparable_years_flags_missing_endpoints():
    assert calc.check_comparable_years({"A": {2015: 1, 2025: 2}, "B": {2016: 1, 2025: 2}}, 2015, 2025) == ["B"]


def test_illustrative_projection_is_labelled_and_exponential():
    p = calc.illustrative_projection(8e9, date(2025, 7, 1), 1.0, date(2026, 7, 1))
    assert p.value_kind == ValueKind.ILLUSTRATIVE_PROJECTION
    days = (date(2026, 7, 1) - date(2025, 7, 1)).days
    assert p.value == pytest.approx(8e9 * math.exp(0.01 * days / 365.2425))
    assert any("not an official" in a for a in p.assumptions)


def test_illustrative_projection_rejects_implausible_rates():
    with pytest.raises(CalculationError):
        calc.illustrative_projection(8e9, date(2025, 7, 1), 25.0, date(2026, 1, 1))


def test_formatting_is_stable():
    assert fmt_people(1_463_865_525) == "1.46 billion"
    assert fmt_people(237_500_000) == "237.5 million"
    assert fmt_people(None) == "Data unavailable"
    assert fmt_pct(-0.171, 2, signed=True) == "-0.17%"
