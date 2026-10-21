import json
from datetime import date

import pytest
from sqlalchemy import select

from app.domain.errors import DuplicateImportError, ImportValidationError
from app.domain.validation import assess_freshness, parse_year, validate_rows
from app.ingestion.importer import ImportOptions, import_snapshot
from app.repositories.orm import CountryBaselineRow, SourceEventRow
from app.repositories.population import PopulationRepository
from app.services.population import PopulationService
from tests.conftest import COUNTRIES, make_snapshot, synthetic_rows

METRICS = {"population_total": "persons", "urban_pct": "%"}
KNOWN = {"IND", "PAK"}


def _events(factory) -> list[str]:
    with factory() as s:
        return [e.event_type for e in s.scalars(select(SourceEventRow).order_by(SourceEventRow.id))]


@pytest.mark.parametrize("raw", ["2020-01-01", "20", "FY2020", "", "2020.0", "1800"])
def test_parse_year_rejects_unsupported_formats(raw):
    with pytest.raises(ValueError):
        parse_year(raw)


def test_validate_rows_rejects_bad_rows_with_reasons():
    rows = [
        {"country_iso3": "IND", "metric": "population_total", "year": "2020", "value": "1000"},
        {"country_iso3": "", "metric": "population_total", "year": "2020", "value": "5"},
        {"country_iso3": "IND", "metric": "population_total", "year": "2021", "value": "-5"},
        {"country_iso3": "IND", "metric": "population_total", "year": "2022", "value": "12.5"},
        {"country_iso3": "IND", "metric": "population_total", "year": "2023", "value": "abc"},
        {"country_iso3": "IND", "metric": "population_total", "year": "2020", "value": "1001"},
        {"country_iso3": "ZZZ", "metric": "population_total", "year": "2020", "value": "1"},
        {"country_iso3": "PAK", "metric": "urban_pct", "year": "2020", "value": "140"},
        {"country_iso3": "PAK", "metric": "population_total", "year": "20/01/2020", "value": "1"},
    ]
    res = validate_rows(rows, KNOWN, METRICS)
    assert len(res.accepted) == 1
    reasons = [r["reason"] for r in res.rejected]
    assert "missing country code" in reasons
    assert "population must be positive" in reasons
    assert "population must be a whole number of persons" in reasons
    assert any("non-numeric" in r for r in reasons)
    assert "duplicate row for country/metric/year" in reasons
    assert any("unknown country code" in r for r in reasons)
    assert "percentage outside 0-100" in reasons
    assert any("unsupported date format" in r for r in reasons)


def test_import_success_records_provenance_and_estimates(factory, loaded):
    assert loaded.rows_rejected == 0 and loaded.coverage["complete"]
    with factory() as s:
        repo = PopulationRepository(s)
        src = repo.active_source()
        assert src.snapshot_id == "synthetic-2026-01-01" and src.is_synthetic
        assert len(src.checksum) == 64
        est = repo.estimate(src.id, "WLD")
        assert est.reference_date == date(2025, 7, 1) and est.value_kind == "estimate"
    assert _events(factory)[-1] == "import_succeeded"


def test_duplicate_import_rejected_and_audited(factory, loaded, tmp_path):
    with pytest.raises(DuplicateImportError):
        import_snapshot(factory, tmp_path / "snapshots" / "synthetic-2026-01-01")
    assert _events(factory)[-1] == "import_rejected"


def test_invalid_rows_reject_whole_import_unless_skip_invalid(factory, tmp_path):
    rows = synthetic_rows()
    rows.append({"country_iso3": "IND", "indicator_code": "SP.POP.TOTL", "metric": "population_total",
                 "unit": "persons", "year": "2015", "value": "1"})  # duplicate observation
    rows.append({"country_iso3": "", "indicator_code": "SP.POP.TOTL", "metric": "population_total",
                 "unit": "persons", "year": "2016", "value": "1"})  # missing code
    snap = make_snapshot(tmp_path, "bad-rows", rows=rows)
    with pytest.raises(ImportValidationError) as exc:
        import_snapshot(factory, snap)
    assert len(exc.value.rejected) == 2
    with factory() as s:
        assert s.scalar(select(CountryBaselineRow.id).limit(1)) is None  # nothing written (transaction rolled back)
    result = import_snapshot(factory, snap, ImportOptions(skip_invalid=True))
    assert result.rows_rejected == 2
    assert "rows_rejected" in _events(factory)


def test_tampered_snapshot_fails_checksum(factory, tmp_path):
    snap = make_snapshot(tmp_path, "tampered")
    with (snap / "indicators.csv").open("a") as fh:
        fh.write("IND,SP.POP.TOTL,population_total,persons,2030,5\n")
    with pytest.raises(ImportValidationError, match="checksum mismatch"):
        import_snapshot(factory, snap)


def test_missing_manifest_fields_rejected(factory, tmp_path):
    snap = make_snapshot(tmp_path, "no-license", license="")
    with pytest.raises(ImportValidationError, match="license"):
        import_snapshot(factory, snap)


def test_incomplete_coverage_below_threshold_rejected(factory, tmp_path):
    rows = [r for r in synthetic_rows() if not (r["country_iso3"] in ("PAK", "LKA") and r["metric"] == "population_total")]
    snap = make_snapshot(tmp_path, "low-coverage", rows=rows)
    with pytest.raises(ImportValidationError, match="coverage"):
        import_snapshot(factory, snap)


def test_incomplete_coverage_above_threshold_recorded(factory, tmp_path):
    rows = [r for r in synthetic_rows() if not (r["country_iso3"] == "BTN" and r["metric"] == "population_total")]
    snap = make_snapshot(tmp_path, "partial-coverage", rows=rows)
    result = import_snapshot(factory, snap, ImportOptions(min_coverage=0.7))
    assert result.coverage["missing"] == ["BTN"] and not result.coverage["complete"]
    assert "incomplete_coverage" in _events(factory)


def test_baseline_replacement_supersedes_previous_source(factory, loaded, tmp_path):
    rows = synthetic_rows(years=range(2016, 2027))
    snap = make_snapshot(tmp_path, "synthetic-2027-01-01", rows=rows)
    result = import_snapshot(factory, snap)
    assert result.replaced_source_ids == [loaded.source_id]
    with factory() as s:
        repo = PopulationRepository(s)
        active = repo.active_source()
        assert active.snapshot_id == "synthetic-2027-01-01"
        old = [x for x in repo.list_sources() if x.id == loaded.source_id][0]
        assert not old.is_active
        assert repo.estimate(active.id, "WLD").reference_date == date(2026, 7, 1)
    assert "baseline_replaced" in _events(factory)


def test_stale_data_is_flagged(factory, tmp_path):
    snap = make_snapshot(tmp_path, "old-data", rows=synthetic_rows(years=range(2005, 2016)))
    result = import_snapshot(factory, snap, ImportOptions(today=date(2026, 10, 1), stale_after_days=730))
    assert result.freshness["status"] == "stale"
    assert "stale_data_warning" in _events(factory)
    with factory() as s:
        summary = PopulationService(PopulationRepository(s), 730, today=date(2026, 10, 1)).world_summary()
    assert summary.provenance.freshness.status == "stale"


def test_freshness_unknown_without_data():
    assert assess_freshness(None, date(2026, 1, 1), 730)["status"] == "unknown"


def test_invalid_country_records_rejected(factory, tmp_path):
    bad = COUNTRIES + [{"iso3": "", "name": "Nowhere"}]
    snap = make_snapshot(tmp_path, "bad-country", countries=bad)
    with pytest.raises(ImportValidationError, match="country records invalid"):
        import_snapshot(factory, snap)
    assert json.loads((snap / "manifest.json").read_text())["snapshot_id"] == "bad-country"
