"""Shared fixtures. Test data is SYNTHETIC (manifest is_synthetic=true) and only used in tests."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import BACKEND_DIR, Settings
from app.db import make_engine, run_migrations
from app.ingestion.importer import ImportOptions, import_snapshot
from app.integrations.llm import LLMError, LLMResult

INDICATORS = {
    "SP.POP.TOTL": ("population_total", "persons"),
    "SP.POP.GROW": ("population_growth_pct", "% per year"),
    "SP.DYN.TFRT.IN": ("fertility_rate", "births per woman"),
    "SP.DYN.LE00.IN": ("life_expectancy_years", "years"),
    "SP.DYN.CBRT.IN": ("birth_rate_per_1000", "births per 1,000 people"),
    "SP.DYN.CDRT.IN": ("death_rate_per_1000", "deaths per 1,000 people"),
    "SP.POP.0014.TO.ZS": ("age_0_14_pct", "% of total population"),
    "SP.POP.1564.TO.ZS": ("age_15_64_pct", "% of total population"),
    "SP.POP.65UP.TO.ZS": ("age_65_plus_pct", "% of total population"),
    "SP.URB.TOTL.IN.ZS": ("urban_pct", "% of total population"),
    "SP.RUR.TOTL.ZS": ("rural_pct", "% of total population"),
    "EN.POP.DNST": ("density_per_km2", "people per sq. km of land area"),
    "AG.LND.TOTL.K2": ("land_area_km2", "sq. km"),
    "SM.POP.NETM": ("net_migration", "persons (net, annual)"),
}
CODE = {m: c for c, (m, _) in INDICATORS.items()}

COUNTRIES = [
    {"iso3": "WLD", "iso2": "1W", "name": "World", "region_code": None, "region": "Aggregates", "is_aggregate": True},
    {"iso3": "SAS", "iso2": "8S", "name": "South Asia", "region_code": None, "region": "Aggregates", "is_aggregate": True},
    {"iso3": "IND", "iso2": "IN", "name": "India", "region_code": "SAS", "region": "South Asia",
     "income_level": "Lower middle income", "capital": "New Delhi", "is_aggregate": False},
    {"iso3": "PAK", "iso2": "PK", "name": "Pakistan", "region_code": "SAS", "region": "South Asia",
     "income_level": "Lower middle income", "capital": "Islamabad", "is_aggregate": False},
    {"iso3": "LKA", "iso2": "LK", "name": "Sri Lanka", "region_code": "SAS", "region": "South Asia",
     "income_level": "Lower middle income", "capital": "Colombo", "is_aggregate": False},
    {"iso3": "BTN", "iso2": "BT", "name": "Bhutan", "region_code": "SAS", "region": "South Asia",
     "income_level": "Lower middle income", "capital": "Thimphu", "is_aggregate": False},
]
# Synthetic base populations and growth rates (NOT real statistics).
BASE = {"IND": (1_000_000_000, 1.0), "PAK": (200_000_000, 2.0), "LKA": (20_000_000, 0.5), "BTN": (700_000, 1.2)}


def synthetic_rows(years=range(2015, 2026), skip: set[tuple[str, str]] | None = None) -> list[dict]:
    skip = skip or set()
    rows = []
    totals: dict[int, float] = {}
    sas: dict[int, float] = {}
    for iso3, (base, g) in BASE.items():
        for i, y in enumerate(years):
            pop = round(base * (1 + g / 100) ** i)
            totals[y] = totals.get(y, 0) + pop
            if iso3 != "BTN":
                sas[y] = sas.get(y, 0) + pop
            vals = {
                "population_total": pop, "population_growth_pct": g, "fertility_rate": 3.0 - 0.05 * i,
                "life_expectancy_years": 68 + 0.2 * i, "birth_rate_per_1000": 20 - 0.3 * i,
                "death_rate_per_1000": 7 + 0.05 * i, "age_0_14_pct": 30 - 0.4 * i, "age_15_64_pct": 63.0,
                "age_65_plus_pct": 7 + 0.4 * i, "urban_pct": 35 + 0.5 * i, "rural_pct": 65 - 0.5 * i,
                "land_area_km2": 1_000_000.0, "density_per_km2": pop / 1_000_000.0, "net_migration": -10000 + i * 100,
            }
            for metric, v in vals.items():
                if (iso3, metric) in skip or (metric == "net_migration" and iso3 == "BTN"):
                    continue
                if metric in ("fertility_rate", "life_expectancy_years", "birth_rate_per_1000",
                              "death_rate_per_1000") and y == max(years):
                    continue  # vital rates lag one year, as in WDI
                rows.append({"country_iso3": iso3, "indicator_code": CODE[metric], "metric": metric,
                             "unit": INDICATORS[CODE[metric]][1], "year": str(y), "value": str(v)})
    for scope, series in (("WLD", {y: v * 4 for y, v in totals.items()}), ("SAS", sas)):
        for y, v in series.items():
            rows.append({"country_iso3": scope, "indicator_code": "SP.POP.TOTL", "metric": "population_total",
                         "unit": "persons", "year": str(y), "value": str(v)})
            rows.append({"country_iso3": scope, "indicator_code": "SP.POP.GROW", "metric": "population_growth_pct",
                         "unit": "% per year", "year": str(y), "value": "0.9"})
    return rows


def make_snapshot(root: Path, snapshot_id: str = "synthetic-2026-01-01", rows: list[dict] | None = None,
                  countries: list[dict] | None = None, **manifest_overrides) -> Path:
    d = root / snapshot_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "countries.json").write_text(json.dumps(countries if countries is not None else COUNTRIES), encoding="utf-8")
    rows = rows if rows is not None else synthetic_rows()
    with (d / "indicators.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["country_iso3", "indicator_code", "metric", "unit", "year", "value"])
        w.writeheader()
        w.writerows(rows)
    manifest = {
        "snapshot_id": snapshot_id, "dataset_name": "Synthetic test dataset", "publisher": "TerraPulse tests",
        "source_url": "https://example.invalid/synthetic", "landing_page": None, "license": "CC0 (synthetic)",
        "release_version": snapshot_id[-10:], "retrieved_at": "2026-01-01T00:00:00+00:00",
        "reference_date_convention": "Midyear (1 July)", "geographic_coverage": "Synthetic",
        "methodology_notes": "Synthetic values for automated tests.", "value_kind": "estimate",
        "uncertainty": "Not quantified (synthetic).", "is_synthetic": True,
        "indicators": {k: {"metric": m, "unit": u} for k, (m, u) in INDICATORS.items()}, "files": {},
    }
    manifest.update(manifest_overrides)
    for name in ("countries.json", "indicators.csv"):
        manifest["files"][name] = {"sha256": hashlib.sha256((d / name).read_bytes()).hexdigest()}
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return d


def make_cities(d: Path) -> Path:
    """Synthetic GeoNames-style city snapshot, stored largest population first like the real one."""
    snap = d / "geonames-2026-01-01"
    snap.mkdir(parents=True)
    rows = [["1", "Mumbai", "", "IN", "Maharashtra", "12691836", "2026-01-01"],
            ["2", "São Paulo", "Sao Paulo", "BR", "São Paulo", "12400232", "2026-01-01"],
            ["3", "Punemara", "", "IN", "Synthetic", "900000", "2026-01-01"],
            ["4", "Pune", "", "IN", "Maharashtra", "300000", "2026-01-01"]]
    with (snap / "cities.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["geonameid", "name", "asciiname", "country_iso2", "admin1", "population", "modified"])
        w.writerows(rows)
    (snap / "manifest.json").write_text(json.dumps({
        "snapshot_id": snap.name, "dataset_name": "Synthetic cities", "publisher": "TerraPulse tests",
        "source_url": "https://example.invalid/cities", "landing_page": None, "license": "CC0 (synthetic)",
        "retrieved_at": "2026-01-01T00:00:00+00:00", "value_kind": "estimate",
        "reference_date_convention": "Not specified (synthetic).",
    }), encoding="utf-8")
    return d


class FakeLLM:
    """Scriptable stand-in for Claude. Each call pops the next response (str) or raises it (Exception)."""

    model = "fake-claude"

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str, max_tokens: int) -> LLMResult:
        self.calls.append((system, user))
        r = self.responses.pop(0) if self.responses else LLMError("no scripted response")
        if isinstance(r, Exception):
            raise r
        return LLMResult(text=r, model=self.model, stop_reason="end_turn", input_tokens=1, output_tokens=1,
                         latency_ms=1.0)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path / 'test.db'}", anthropic_api_key=None,
        storage_dir=tmp_path / "reports", report_execution="inline", methodology_dir=BACKEND_DIR / "data" / "methodology",
        log_level="WARNING", max_active_reports_per_user=5, city_dir=make_cities(tmp_path / "cities"),
    )


@pytest.fixture
def factory(settings: Settings) -> sessionmaker:
    run_migrations(settings.database_url)
    return sessionmaker(bind=make_engine(settings.database_url), expire_on_commit=False)


@pytest.fixture
def loaded(factory, tmp_path: Path):
    snap = make_snapshot(tmp_path / "snapshots")
    return import_snapshot(factory, snap, ImportOptions(today=date(2026, 1, 1)))


def _client(settings, factory, llm=None) -> TestClient:
    from app.main import build_container, create_app

    container = build_container(settings, factory, llm=llm, use_llm_from_settings=False)
    return TestClient(create_app(container))


@pytest.fixture
def client(settings, factory, loaded):
    with _client(settings, factory) as c:
        yield c


@pytest.fixture
def empty_client(settings, factory):
    with _client(settings, factory) as c:
        yield c


@pytest.fixture
def client_factory(settings, factory, loaded):
    def make(llm=None):
        return _client(settings, factory, llm)

    return make
