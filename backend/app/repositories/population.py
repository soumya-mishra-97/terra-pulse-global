"""Population data repository. All SQL is built with SQLAlchemy expressions (bound parameters)."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.domain.models import Country, DataSource
from app.repositories.orm import (
    CalculationRunRow,
    CountryBaselineRow,
    CountryRow,
    DataSourceRow,
    PopulationEstimateRow,
    SourceEventRow,
)


def _country(row: CountryRow) -> Country:
    return Country(
        iso3=row.iso3, iso2=row.iso2, name=row.name, region_code=row.region_code, region=row.region,
        income_level=row.income_level, capital=row.capital, latitude=row.latitude, longitude=row.longitude,
        is_aggregate=row.is_aggregate,
    )


def _source(row: DataSourceRow) -> DataSource:
    imported = row.imported_at if row.imported_at.tzinfo else row.imported_at.replace(tzinfo=UTC)
    return DataSource(
        id=row.id, snapshot_id=row.snapshot_id, dataset_name=row.dataset_name, publisher=row.publisher,
        source_url=row.source_url, license=row.license, release_version=row.release_version, imported_at=imported,
        checksum=row.checksum, geographic_coverage=row.geographic_coverage, methodology_notes=row.methodology_notes,
        uncertainty_note=row.uncertainty_note, reference_date_convention=row.reference_date_convention,
        is_active=row.is_active, is_synthetic=row.is_synthetic, landing_page=row.landing_page,
    )


class PopulationRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    # ---- sources -------------------------------------------------------------
    def active_source(self) -> DataSource | None:
        row = self.s.scalar(select(DataSourceRow).where(DataSourceRow.is_active.is_(True)).order_by(DataSourceRow.id.desc()))
        return _source(row) if row else None

    def list_sources(self) -> list[DataSource]:
        return [_source(r) for r in self.s.scalars(select(DataSourceRow).order_by(DataSourceRow.id.desc()))]

    def source_by_checksum(self, checksum: str) -> DataSource | None:
        row = self.s.scalar(select(DataSourceRow).where(DataSourceRow.checksum == checksum))
        return _source(row) if row else None

    def source_by_snapshot(self, snapshot_id: str) -> DataSource | None:
        row = self.s.scalar(select(DataSourceRow).where(DataSourceRow.snapshot_id == snapshot_id))
        return _source(row) if row else None

    def source_coverage(self, source_id: int) -> dict:
        return self.s.scalar(select(DataSourceRow.coverage).where(DataSourceRow.id == source_id)) or {}

    # ---- countries -----------------------------------------------------------
    def list_countries(self, include_aggregates: bool = False) -> list[Country]:
        stmt = select(CountryRow).order_by(CountryRow.name)
        if not include_aggregates:
            stmt = stmt.where(CountryRow.is_aggregate.is_(False))
        return [_country(r) for r in self.s.scalars(stmt)]

    def get_country(self, iso3: str) -> Country | None:
        row = self.s.get(CountryRow, iso3.upper())
        return _country(row) if row else None

    # ---- observations --------------------------------------------------------
    def series(self, source_id: int, iso3: str, metric: str, start: int | None = None, end: int | None = None) -> dict[int, float]:
        stmt = select(CountryBaselineRow.year, CountryBaselineRow.value).where(
            CountryBaselineRow.source_id == source_id,
            CountryBaselineRow.country_iso3 == iso3,
            CountryBaselineRow.metric == metric,
        )
        if start is not None:
            stmt = stmt.where(CountryBaselineRow.year >= start)
        if end is not None:
            stmt = stmt.where(CountryBaselineRow.year <= end)
        return {y: v for y, v in self.s.execute(stmt.order_by(CountryBaselineRow.year))}

    def all_series(self, source_id: int, iso3: str, start: int | None = None) -> dict[str, dict[int, float]]:
        stmt = select(CountryBaselineRow.metric, CountryBaselineRow.year, CountryBaselineRow.value).where(
            CountryBaselineRow.source_id == source_id, CountryBaselineRow.country_iso3 == iso3
        )
        if start is not None:
            stmt = stmt.where(CountryBaselineRow.year >= start)
        out: dict[str, dict[int, float]] = defaultdict(dict)
        for metric, year, value in self.s.execute(stmt.order_by(CountryBaselineRow.year)):
            out[metric][year] = value
        return dict(out)

    def units(self, source_id: int) -> dict[str, str]:
        stmt = select(CountryBaselineRow.metric, CountryBaselineRow.unit).where(CountryBaselineRow.source_id == source_id).distinct()
        return dict(self.s.execute(stmt).all())

    def latest_year(self, source_id: int, metric: str, iso3: str | None = None) -> int | None:
        stmt = select(func.max(CountryBaselineRow.year)).where(
            CountryBaselineRow.source_id == source_id, CountryBaselineRow.metric == metric
        )
        if iso3:
            stmt = stmt.where(CountryBaselineRow.country_iso3 == iso3)
        return self.s.scalar(stmt)

    def values_for_year(self, source_id: int, metric: str, year: int) -> dict[str, float]:
        stmt = select(CountryBaselineRow.country_iso3, CountryBaselineRow.value).where(
            CountryBaselineRow.source_id == source_id, CountryBaselineRow.metric == metric, CountryBaselineRow.year == year
        )
        return dict(self.s.execute(stmt).all())

    def latest_values(self, source_id: int, metric: str) -> dict[str, tuple[int, float]]:
        """Latest available (year, value) per country for one metric."""
        sub = (
            select(CountryBaselineRow.country_iso3.label("iso3"), func.max(CountryBaselineRow.year).label("y"))
            .where(CountryBaselineRow.source_id == source_id, CountryBaselineRow.metric == metric)
            .group_by(CountryBaselineRow.country_iso3)
            .subquery()
        )
        stmt = select(CountryBaselineRow.country_iso3, CountryBaselineRow.year, CountryBaselineRow.value).join(
            sub, (CountryBaselineRow.country_iso3 == sub.c.iso3) & (CountryBaselineRow.year == sub.c.y)
        ).where(CountryBaselineRow.source_id == source_id, CountryBaselineRow.metric == metric)
        return {iso3: (year, value) for iso3, year, value in self.s.execute(stmt)}

    def estimate(self, source_id: int, scope: str) -> PopulationEstimateRow | None:
        return self.s.scalar(
            select(PopulationEstimateRow)
            .where(PopulationEstimateRow.source_id == source_id, PopulationEstimateRow.scope == scope)
            .order_by(PopulationEstimateRow.reference_date.desc())
        )

    # ---- writes (caller owns the transaction) --------------------------------
    def upsert_countries(self, countries: list[Country]) -> None:
        for c in countries:
            row = self.s.get(CountryRow, c.iso3)
            if row is None:
                row = CountryRow(iso3=c.iso3)
                self.s.add(row)
            row.iso2, row.name, row.region_code, row.region = c.iso2, c.name, c.region_code, c.region
            row.income_level, row.capital, row.latitude, row.longitude = c.income_level, c.capital, c.latitude, c.longitude
            row.is_aggregate = c.is_aggregate
        self.s.flush()

    def add_source(self, **fields) -> DataSourceRow:
        row = DataSourceRow(**fields)
        self.s.add(row)
        self.s.flush()
        return row

    def bulk_insert_baselines(self, rows: list[dict]) -> None:
        if rows:
            self.s.execute(CountryBaselineRow.__table__.insert(), rows)

    def activate_source(self, new_id: int) -> list[int]:
        """Deactivate the previous active source(s) and point them at their replacement."""
        previous = list(self.s.scalars(select(DataSourceRow.id).where(DataSourceRow.is_active.is_(True), DataSourceRow.id != new_id)))
        if previous:
            self.s.execute(
                update(DataSourceRow).where(DataSourceRow.id.in_(previous)).values(is_active=False, superseded_by_id=new_id)
            )
        self.s.execute(update(DataSourceRow).where(DataSourceRow.id == new_id).values(is_active=True))
        return previous

    def add_estimate(self, **fields) -> None:
        self.s.add(PopulationEstimateRow(**fields))

    def add_calculation_run(self, **fields) -> CalculationRunRow:
        row = CalculationRunRow(**fields)
        self.s.add(row)
        self.s.flush()
        return row

    def finish_calculation_run(self, run: CalculationRunRow, status: str, summary: dict) -> None:
        run.status, run.output_summary, run.finished_at = status, summary, datetime.now(UTC)

    def add_event(self, event_type: str, details: dict, source_id: int | None = None) -> None:
        self.s.add(SourceEventRow(event_type=event_type, details=details, source_id=source_id))

    def events(self, limit: int = 50) -> list[SourceEventRow]:
        return list(self.s.scalars(select(SourceEventRow).order_by(SourceEventRow.id.desc()).limit(limit)))

    def delete_source(self, source_id: int) -> None:
        self.s.execute(delete(DataSourceRow).where(DataSourceRow.id == source_id))
