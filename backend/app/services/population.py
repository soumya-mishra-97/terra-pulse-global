"""Application service for population data. The single read path for API, agents and reports."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.domain import calculations as calc
from app.domain.errors import CalculationError, DataUnavailableError, NotFoundError
from app.domain.models import Country, DataSource, reference_date_for_year
from app.domain.validation import assess_freshness
from app.repositories.population import PopulationRepository
from app.schemas.population import (
    ChangeOut,
    CountryListItem,
    CountryPage,
    Estimate,
    Freshness,
    HistoryPoint,
    HistoryResponse,
    IllustrativeCounter,
    Provenance,
    RankedCountry,
    RegionsResponse,
    RegionStat,
    WorldSummary,
    YearValue,
)

WORLD = "WLD"
METRICS = (
    "population_total", "population_growth_pct", "birth_rate_per_1000", "death_rate_per_1000", "fertility_rate",
    "life_expectancy_years", "age_0_14_pct", "age_15_64_pct", "age_65_plus_pct", "urban_pct", "rural_pct",
    "density_per_km2", "land_area_km2", "net_migration",
)
SORTS = {"name", "population", "growth", "share"}


class PopulationService:
    def __init__(self, repo: PopulationRepository, stale_after_days: int = 730, today: date | None = None) -> None:
        self.repo = repo
        self.stale_after_days = stale_after_days
        self.today = today or datetime.now(UTC).date()

    # ---- provenance ----------------------------------------------------------
    def source(self) -> DataSource:
        src = self.repo.active_source()
        if src is None:
            raise DataUnavailableError("No population dataset has been imported yet. Run the import CLI.")
        return src

    def provenance(self, src: DataSource, reference_year: int | None) -> Provenance:
        fresh = assess_freshness(reference_year, self.today, self.stale_after_days)
        return Provenance(
            source_id=src.id, snapshot_id=src.snapshot_id, dataset_name=src.dataset_name, publisher=src.publisher,
            source_url=src.source_url, landing_page=src.landing_page, license=src.license,
            release_version=src.release_version, imported_at=src.imported_at,
            reference_date=reference_date_for_year(reference_year) if reference_year else None,
            value_kind="estimate", uncertainty_note=src.uncertainty_note,
            freshness=Freshness(status=str(fresh["status"]), age_days=fresh["age_days"], stale_after_days=self.stale_after_days),
            is_synthetic=src.is_synthetic,
            data_label=("DEMO DATA - synthetic values, not real statistics" if src.is_synthetic
                        else f"{src.publisher} - {src.dataset_name}, release {src.release_version}"),
        )

    # ---- world summary -------------------------------------------------------
    def world_summary(self) -> WorldSummary:
        src = self.source()
        est = self.repo.estimate(src.id, WORLD)
        if est is None:
            raise DataUnavailableError("The active dataset has no world aggregate.")
        history = self.repo.series(src.id, WORLD, "population_total")
        growth = self.repo.series(src.id, WORLD, "population_growth_pct")
        latest_year = est.reference_date.year
        prev = history.get(latest_year - 1)
        annual_change = est.value - prev if prev else None
        annual_pct = calc.percent_change(prev, est.value) if prev else None
        g_year = max(growth) if growth else None

        counter = None
        if g_year is not None:
            try:
                p = calc.illustrative_projection(est.value, est.reference_date, growth[g_year], est.reference_date)
                counter = IllustrativeCounter(
                    base_value=p.base_value, base_date=p.base_date, annual_growth_percent=p.annual_growth_percent,
                    assumptions=list(p.assumptions),
                )
            except CalculationError:
                counter = None

        countries = {c.iso3: c for c in self.repo.list_countries()}
        pops = self.repo.values_for_year(src.id, "population_total", latest_year)
        top = calc.rank_desc({k: v for k, v in pops.items() if k in countries})[:10]
        growth_latest = self.repo.values_for_year(src.id, "population_growth_pct", g_year) if g_year else {}
        # Ignore micro-states for the "fastest growing" list to avoid noisy rankings.
        fast = calc.rank_desc({k: v for k, v in growth_latest.items() if k in countries and pops.get(k, 0) >= 1_000_000})[:5]
        return WorldSummary(
            estimate=Estimate(value=est.value, reference_date=est.reference_date, value_kind=est.value_kind,
                              method=est.method, lower=est.lower, upper=est.upper, uncertainty_note=est.uncertainty_note),
            previous=YearValue(year=latest_year - 1, value=prev) if prev else None,
            annual_change=annual_change, annual_change_percent=annual_pct,
            growth_rate_percent=YearValue(year=g_year, value=growth[g_year]) if g_year else None,
            history=[YearValue(year=y, value=v) for y, v in sorted(history.items())],
            top_countries=[RankedCountry(iso3=k, name=countries[k].name, value=v, year=latest_year) for k, v in top],
            fastest_growing=[RankedCountry(iso3=k, name=countries[k].name, value=v, year=g_year) for k, v in fast],
            country_count=len(countries), coverage=self.repo.source_coverage(src.id),
            illustrative_counter=counter, provenance=self.provenance(src, latest_year),
        )

    # ---- countries -----------------------------------------------------------
    def countries(self, q: str | None = None, region: str | None = None, sort: str = "population",
                  order: str = "desc", limit: int = 50, offset: int = 0) -> CountryPage:
        src = self.source()
        pops = self.repo.latest_values(src.id, "population_total")
        growth = self.repo.latest_values(src.id, "population_growth_pct")
        world = self.repo.estimate(src.id, WORLD)
        needle = q.lower() if q else None
        items = []
        for c in self.repo.list_countries():
            # Matches the country name, its capital city, or its ISO3 code.
            if needle and not (needle in c.name.lower() or needle in (c.capital or "").lower()
                               or needle.upper() == c.iso3):
                continue
            if region and region not in (c.region_code, c.region):
                continue
            py, pv = pops.get(c.iso3, (None, None))
            gy, gv = growth.get(c.iso3, (None, None))
            share = calc.share_percent(pv, world.value) if pv and world and py == world.reference_date.year else None
            items.append(CountryListItem(
                iso3=c.iso3, iso2=c.iso2, name=c.name, region=c.region, region_code=c.region_code,
                income_level=c.income_level, capital=c.capital, population=pv, population_year=py, growth_percent=gv, growth_year=gy,
                share_of_world_percent=share,
            ))
        attr = {"name": "name", "population": "population", "growth": "growth_percent",
                "share": "share_of_world_percent"}[sort if sort in SORTS else "population"]
        present = sorted((i for i in items if getattr(i, attr) is not None), key=lambda i: getattr(i, attr),
                         reverse=(order == "desc"))
        items = present + [i for i in items if getattr(i, attr) is None]  # missing values always last
        ref_year = world.reference_date.year if world else None
        return CountryPage(items=items[offset: offset + limit], total=len(items), limit=limit, offset=offset,
                           provenance=self.provenance(src, ref_year))

    def country(self, iso3: str) -> Country:
        c = self.repo.get_country(iso3)
        if c is None:
            raise NotFoundError(f"Unknown country code {iso3!r}")
        return c

    def history(self, iso3: str, metric: str = "population_total", start: int | None = None, end: int | None = None) -> HistoryResponse:
        if metric not in METRICS:
            raise NotFoundError(f"Unsupported metric {metric!r}")
        src = self.source()
        c = self.country(iso3)
        series = self.repo.series(src.id, c.iso3, metric, start, end)
        change = None
        if len(series) >= 2:
            try:
                ch = calc.change_over_period(series)
                change = ChangeOut(start_year=ch.start_year, end_year=ch.end_year, absolute=ch.absolute,
                                   percent=ch.percent, cagr_percent=ch.cagr_percent)
            except CalculationError:
                change = None
        return HistoryResponse(
            iso3=c.iso3, name=c.name, metric=metric, unit=self.repo.units(src.id).get(metric, ""),
            value_kind="estimate",
            points=[HistoryPoint(year=y, value=v, reference_date=reference_date_for_year(y)) for y, v in sorted(series.items())],
            change=change, provenance=self.provenance(src, max(series) if series else None),
        )

    def regions(self) -> RegionsResponse:
        src = self.source()
        region_codes = sorted({c.region_code for c in self.repo.list_countries() if c.region_code})
        aggregates = {c.iso3: c for c in self.repo.list_countries(include_aggregates=True) if c.is_aggregate}
        stats = [self._region_stat(src.id, code, aggregates[code].name) for code in region_codes if code in aggregates]
        world = self._region_stat(src.id, WORLD, "World") if WORLD in aggregates else None
        return RegionsResponse(regions=stats, world=world, provenance=self.provenance(src, world.year if world else None))

    def _region_stat(self, source_id: int, code: str, name: str) -> RegionStat:
        data = self.repo.all_series(source_id, code)

        def latest(metric: str) -> float | None:
            s = data.get(metric) or {}
            return s[max(s)] if s else None

        pop = data.get("population_total") or {}
        return RegionStat(
            code=code, name=name, year=max(pop) if pop else None, population=latest("population_total"),
            growth_percent=latest("population_growth_pct"), age_0_14_pct=latest("age_0_14_pct"),
            age_15_64_pct=latest("age_15_64_pct"), age_65_plus_pct=latest("age_65_plus_pct"),
            urban_pct=latest("urban_pct"), fertility_rate=latest("fertility_rate"),
            life_expectancy_years=latest("life_expectancy_years"),
        )

    # ---- agent/report helpers (structured, deterministic) --------------------
    def country_profile(self, iso3: str, start_year: int | None = None) -> dict:
        """Everything the agents need about one country, with units and provenance."""
        src = self.source()
        c = self.country(iso3)
        series = self.repo.all_series(src.id, c.iso3, start_year)
        units = self.repo.units(src.id)
        latest = {m: {"year": max(s), "value": s[max(s)], "unit": units.get(m, "")} for m, s in series.items() if s}
        return {"country": c, "series": series, "latest": latest, "units": units, "source": src}

    def resolve_country(self, text: str) -> Country | None:
        text_l = text.strip().lower()
        for c in self.repo.list_countries(include_aggregates=True):
            if text_l in (c.name.lower(), c.iso3.lower()) or (c.iso2 and text_l == c.iso2.lower() and not c.is_aggregate):
                return c
        return None

    def all_countries(self, include_aggregates: bool = False) -> list[Country]:
        return self.repo.list_countries(include_aggregates)

    def latest_values(self, metric: str) -> dict[str, tuple[int, float]]:
        return self.repo.latest_values(self.source().id, metric)

    def values_for_year(self, metric: str, year: int) -> dict[str, float]:
        return self.repo.values_for_year(self.source().id, metric, year)

    def series(self, iso3: str, metric: str, start: int | None = None, end: int | None = None) -> dict[int, float]:
        return self.repo.series(self.source().id, iso3, metric, start, end)
