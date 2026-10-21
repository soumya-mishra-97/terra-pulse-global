"""Versioned, repeatable import of a dated dataset snapshot into PostgreSQL.

A snapshot directory contains manifest.json, countries.json and indicators.csv (see
scripts/fetch_worldbank_snapshot.py). The import is all-or-nothing: it runs in one
transaction, and the previous active source is only superseded when the new one commits.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import DuplicateImportError, ImportValidationError
from app.domain.models import Country, ValueKind, reference_date_for_year
from app.domain.validation import ISO3_RE, assess_freshness, coverage_report, validate_rows
from app.repositories.population import PopulationRepository

log = logging.getLogger(__name__)

REQUIRED_MANIFEST_FIELDS = (
    "snapshot_id", "dataset_name", "publisher", "source_url", "license", "release_version",
    "retrieved_at", "reference_date_convention", "geographic_coverage", "methodology_notes",
    "uncertainty", "indicators", "files",
)
REQUIRED_FILES = ("countries.json", "indicators.csv")


@dataclass
class ImportOptions:
    skip_invalid: bool = False
    min_coverage: float = 0.9
    stale_after_days: int = 730
    today: date = field(default_factory=lambda: datetime.now(UTC).date())


@dataclass
class ImportResult:
    source_id: int
    snapshot_id: str
    rows_imported: int
    rows_rejected: int
    countries: int
    coverage: dict
    freshness: dict
    replaced_source_ids: list[int]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(snapshot_dir: Path) -> dict:
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ImportValidationError(f"manifest.json not found in {snapshot_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [f for f in REQUIRED_MANIFEST_FIELDS if not manifest.get(f)]
    if missing:
        raise ImportValidationError(f"manifest missing required fields: {', '.join(missing)}")
    for name in REQUIRED_FILES:
        path = snapshot_dir / name
        if not path.is_file():
            raise ImportValidationError(f"snapshot file {name} is missing")
        expected = manifest["files"].get(name, {}).get("sha256")
        if not expected or expected != _sha256(path):
            raise ImportValidationError(f"checksum mismatch for {name}; snapshot may be corrupted or edited")
    return manifest


def snapshot_checksum(manifest: dict) -> str:
    joined = "|".join(f"{n}:{manifest['files'][n]['sha256']}" for n in sorted(REQUIRED_FILES))
    return hashlib.sha256(joined.encode()).hexdigest()


def _load_countries(snapshot_dir: Path) -> tuple[list[Country], list[dict]]:
    raw = json.loads((snapshot_dir / "countries.json").read_text(encoding="utf-8"))
    ok, bad = [], []
    for item in raw:
        iso3 = (item.get("iso3") or "").strip().upper()
        name = " ".join((item.get("name") or "").split())  # source names can carry stray whitespace
        if not iso3 or not ISO3_RE.match(iso3) or not name:
            bad.append({"reason": "missing or invalid country code/name", "row": item})
            continue
        ok.append(
            Country(
                iso3=iso3, iso2=item.get("iso2"), name=name, region_code=item.get("region_code"),
                region=item.get("region"), income_level=item.get("income_level"), capital=item.get("capital"),
                latitude=item.get("latitude"), longitude=item.get("longitude"), is_aggregate=bool(item.get("is_aggregate")),
            )
        )
    return ok, bad


def import_snapshot(factory: sessionmaker[Session], snapshot_dir: Path, options: ImportOptions | None = None) -> ImportResult:
    options = options or ImportOptions()
    snapshot_dir = Path(snapshot_dir)
    try:
        return _import(factory, snapshot_dir, options)
    except (ImportValidationError, DuplicateImportError) as exc:
        # Record the rejection in its own transaction so it survives the rollback.
        with factory.begin() as s:
            PopulationRepository(s).add_event(
                "import_rejected",
                {"snapshot_dir": snapshot_dir.name, "reason": str(exc),
                 "rejected_rows": getattr(exc, "rejected", [])[:50]},
            )
        log.warning("snapshot import rejected", extra={"snapshot": snapshot_dir.name, "reason": str(exc)})
        raise


def _import(factory: sessionmaker[Session], snapshot_dir: Path, options: ImportOptions) -> ImportResult:
    manifest = load_manifest(snapshot_dir)
    checksum = snapshot_checksum(manifest)
    countries, bad_countries = _load_countries(snapshot_dir)
    if bad_countries and not options.skip_invalid:
        raise ImportValidationError(f"{len(bad_countries)} country records invalid", bad_countries)

    metric_units = {v["metric"]: v["unit"] for v in manifest["indicators"].values()}
    with (snapshot_dir / "indicators.csv").open(encoding="utf-8", newline="") as fh:
        validation = validate_rows(csv.DictReader(fh), {c.iso3 for c in countries}, metric_units)
    if validation.rejected and not options.skip_invalid:
        raise ImportValidationError(
            f"{len(validation.rejected)} invalid rows (first: line {validation.rejected[0]['line']}: "
            f"{validation.rejected[0]['reason']}). Re-run with --skip-invalid to import valid rows only.",
            validation.rejected,
        )
    if not validation.accepted:
        raise ImportValidationError("snapshot contains no valid observations")

    real_countries = {c.iso3 for c in countries if not c.is_aggregate}
    pop_rows = [b for b in validation.accepted if b.metric == "population_total"]
    latest_year = max((b.year for b in pop_rows), default=None)
    coverage = coverage_report([b for b in pop_rows if b.year == latest_year], real_countries)
    coverage["year"] = latest_year
    if coverage["coverage_ratio"] < options.min_coverage:
        raise ImportValidationError(
            f"population coverage {coverage['coverage_ratio']:.1%} for {latest_year} is below the "
            f"required {options.min_coverage:.0%}"
        )
    freshness = assess_freshness(latest_year, options.today, options.stale_after_days)

    with factory.begin() as s:
        repo = PopulationRepository(s)
        if repo.source_by_checksum(checksum) or repo.source_by_snapshot(manifest["snapshot_id"]):
            raise DuplicateImportError(f"snapshot {manifest['snapshot_id']} (checksum {checksum[:12]}) was already imported")

        repo.upsert_countries(countries)
        is_synthetic = bool(manifest.get("is_synthetic", False))
        src = repo.add_source(
            snapshot_id=manifest["snapshot_id"], dataset_name=manifest["dataset_name"], publisher=manifest["publisher"],
            source_url=manifest["source_url"], landing_page=manifest.get("landing_page"), license=manifest["license"],
            release_version=manifest["release_version"], reference_date_convention=manifest["reference_date_convention"],
            geographic_coverage=manifest["geographic_coverage"], methodology_notes=manifest["methodology_notes"],
            uncertainty_note=manifest["uncertainty"], value_kind=manifest.get("value_kind", ValueKind.ESTIMATE.value),
            checksum=checksum, retrieved_at=manifest["retrieved_at"], is_active=False, is_synthetic=is_synthetic,
            row_count=len(validation.accepted), country_count=len(real_countries), coverage=coverage,
        )
        repo.add_event("import_started", {"snapshot_id": manifest["snapshot_id"], "checksum": checksum}, src.id)
        kind = manifest.get("value_kind", ValueKind.ESTIMATE.value)
        batch: list[dict] = []
        for b in validation.accepted:
            batch.append({
                "source_id": src.id, "country_iso3": b.country_iso3, "metric": b.metric, "unit": b.unit,
                "year": b.year, "reference_date": reference_date_for_year(b.year), "value": b.value, "value_kind": kind,
            })
            if len(batch) >= 5000:
                repo.bulk_insert_baselines(batch)
                batch = []
        repo.bulk_insert_baselines(batch)

        run = repo.add_calculation_run(
            kind="derive_latest_estimates", source_id=src.id, inputs_hash=checksum,
            params={"metric": "population_total", "rule": "latest source year per scope, no adjustment"}, status="running",
        )
        derived = 0
        latest_by_scope: dict[str, tuple[int, float]] = {}
        for b in pop_rows:
            if b.country_iso3 not in latest_by_scope or b.year > latest_by_scope[b.country_iso3][0]:
                latest_by_scope[b.country_iso3] = (b.year, b.value)
        for scope, (year, value) in latest_by_scope.items():
            repo.add_estimate(
                source_id=src.id, calculation_run_id=run.id, scope=scope, reference_date=reference_date_for_year(year),
                value=value, value_kind=kind,
                method="Latest source-published midyear value; TerraPulse applies no adjustment.",
                lower=None, upper=None, uncertainty_note=manifest["uncertainty"],
            )
            derived += 1
        repo.finish_calculation_run(run, "succeeded", {"estimates": derived})

        replaced = repo.activate_source(src.id)
        if replaced:
            repo.add_event("baseline_replaced", {"replaced_source_ids": replaced}, src.id)
        if validation.rejected:
            repo.add_event("rows_rejected", {"count": len(validation.rejected), "sample": validation.rejected[:50]}, src.id)
        if not coverage["complete"]:
            repo.add_event("incomplete_coverage", {k: coverage[k] for k in ("year", "coverage_ratio", "missing")}, src.id)
        if freshness["status"] == "stale":
            repo.add_event("stale_data_warning", {"age_days": freshness["age_days"]}, src.id)
        repo.add_event("import_succeeded", {"rows": len(validation.accepted), "estimates": derived}, src.id)
        source_id = src.id

    log.info("snapshot imported", extra={"snapshot": manifest["snapshot_id"], "rows": len(validation.accepted)})
    return ImportResult(
        source_id=source_id, snapshot_id=manifest["snapshot_id"], rows_imported=len(validation.accepted),
        rows_rejected=len(validation.rejected), countries=len(real_countries), coverage=coverage,
        freshness={**freshness, "reference_date": str(freshness["reference_date"])}, replaced_source_ids=replaced,
    )
