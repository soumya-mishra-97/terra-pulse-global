"""City population search over the newest bundled GeoNames snapshot (data/cities/<snapshot_id>/)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from app.domain.errors import DataUnavailableError
from app.repositories.population import PopulationRepository
from app.schemas.population import CityOut, CityPage, CitySource


@dataclass(frozen=True)
class City:
    geonameid: int
    name: str
    ascii_name: str
    country_iso2: str
    admin1: str
    population: int
    modified: str


class CityIndex:
    """In-memory, read-only index; cities.csv is stored largest population first."""

    def __init__(self, manifest: dict, cities: list[City]) -> None:
        self.manifest = manifest
        self.cities = cities
        self._names = [{c.name.lower(), c.ascii_name.lower()} for c in cities]

    @classmethod
    def from_directory(cls, city_dir: Path) -> CityIndex | None:
        snapshots = sorted(p for p in city_dir.glob("*") if (p / "manifest.json").is_file())
        if not snapshots:
            return None
        latest = snapshots[-1]
        with (latest / "cities.csv").open(encoding="utf-8", newline="") as fh:
            cities = [City(int(r["geonameid"]), r["name"], r["asciiname"] or r["name"], r["country_iso2"], r["admin1"],
                           int(r["population"]), r["modified"]) for r in csv.DictReader(fh)]
        return cls(json.loads((latest / "manifest.json").read_text(encoding="utf-8")), cities)

    def search(self, q: str) -> list[City]:
        """Exact name first, then prefix, then substring matches; population order within each group."""
        needle = q.strip().lower()
        ranked = []
        for city, names in zip(self.cities, self._names, strict=True):
            hits = [0 if n == needle else 1 if n.startswith(needle) else 2 for n in names if needle in n]
            if hits:
                ranked.append((min(hits), city))
        ranked.sort(key=lambda m: m[0])  # stable sort keeps population order
        return [c for _, c in ranked]


def search_cities(index: CityIndex | None, repo: PopulationRepository, q: str, limit: int) -> CityPage:
    if index is None:
        raise DataUnavailableError("No city dataset is bundled. Run scripts/fetch_geonames_cities.py.")
    matches = index.search(q)
    countries = {c.iso2: c for c in repo.list_countries() if c.iso2}
    items = []
    for city in matches[:limit]:
        country = countries.get(city.country_iso2)
        items.append(CityOut(
            geonameid=city.geonameid, name=city.name, admin1=city.admin1 or None, country_iso2=city.country_iso2,
            country_iso3=country.iso3 if country else None, country_name=country.name if country else None,
            population=city.population, record_modified=city.modified,
        ))
    return CityPage(items=items, total=len(matches), source=CitySource(**index.manifest))
