"""Download a dated snapshot of World Bank World Development Indicators (WDI).

Source: World Bank Open Data API v2 (https://api.worldbank.org/v2), licensed CC BY 4.0.
The snapshot is written to data/snapshots/<snapshot_id>/ together with a manifest that
records the source URL, the API's own `lastupdated` date per indicator, the retrieval
time and SHA-256 checksums. Import it afterwards with:

    python -m app.ingestion.cli import-snapshot data/snapshots/<snapshot_id>

Run with: python scripts/fetch_worldbank_snapshot.py [--start 2000] [--end 2025]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.worldbank.org/v2"

# indicator code -> (internal metric key, unit)
INDICATORS: dict[str, tuple[str, str]] = {
    "SP.POP.TOTL": ("population_total", "persons"),
    "SP.POP.GROW": ("population_growth_pct", "% per year"),
    "SP.DYN.CBRT.IN": ("birth_rate_per_1000", "births per 1,000 people"),
    "SP.DYN.CDRT.IN": ("death_rate_per_1000", "deaths per 1,000 people"),
    "SP.DYN.TFRT.IN": ("fertility_rate", "births per woman"),
    "SP.DYN.LE00.IN": ("life_expectancy_years", "years"),
    "SP.POP.0014.TO.ZS": ("age_0_14_pct", "% of total population"),
    "SP.POP.1564.TO.ZS": ("age_15_64_pct", "% of total population"),
    "SP.POP.65UP.TO.ZS": ("age_65_plus_pct", "% of total population"),
    "SP.URB.TOTL.IN.ZS": ("urban_pct", "% of total population"),
    "SP.RUR.TOTL.ZS": ("rural_pct", "% of total population"),
    "EN.POP.DNST": ("density_per_km2", "people per sq. km of land area"),
    "AG.LND.TOTL.K2": ("land_area_km2", "sq. km"),
    "SM.POP.NETM": ("net_migration", "persons (net, annual)"),
}


def _get(url: str, attempts: int = 4) -> list:
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:  # noqa: S310 - fixed https host
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # bounded retry with backoff
            if attempt == attempts:
                raise
            print(f"  retry {attempt} after error: {exc}", file=sys.stderr)
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2000)
    parser.add_argument("--end", type=int, default=2025)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "snapshots"))
    args = parser.parse_args()

    print("Fetching country metadata ...")
    meta = _get(f"{API}/country?format=json&per_page=400")
    countries = []
    for c in meta[1]:
        countries.append(
            {
                "iso3": c["id"],
                "iso2": c["iso2Code"],
                "name": c["name"],
                "region_code": c["region"]["id"] or None,
                "region": c["region"]["value"].strip() or None,
                "income_level": c["incomeLevel"]["value"].strip() or None,
                "capital": c["capitalCity"] or None,
                "latitude": float(c["latitude"]) if c["latitude"] else None,
                "longitude": float(c["longitude"]) if c["longitude"] else None,
                "is_aggregate": c["region"]["value"] == "Aggregates",
            }
        )

    rows: list[dict] = []
    last_updated: dict[str, str] = {}
    for code, (metric, unit) in INDICATORS.items():
        print(f"Fetching {code} ({metric}) ...")
        payload = _get(f"{API}/country/all/indicator/{code}?format=json&per_page=20000&date={args.start}:{args.end}")
        header, data = payload[0], payload[1] or []
        last_updated[code] = header.get("lastupdated", "")
        for d in data:
            if d["value"] is None or not d["countryiso3code"]:
                continue
            rows.append(
                {
                    "country_iso3": d["countryiso3code"],
                    "indicator_code": code,
                    "metric": metric,
                    "unit": unit,
                    "year": d["date"],
                    "value": d["value"],
                }
            )

    lu = max(last_updated.values()) or datetime.now(UTC).date().isoformat()
    snapshot_id = f"wdi-{lu}"
    out = Path(args.out) / snapshot_id
    out.mkdir(parents=True, exist_ok=True)

    (out / "countries.json").write_text(json.dumps(countries, indent=1, ensure_ascii=False), encoding="utf-8")
    with (out / "indicators.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["country_iso3", "indicator_code", "metric", "unit", "year", "value"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["country_iso3"], r["indicator_code"], r["year"])))

    manifest = {
        "snapshot_id": snapshot_id,
        "dataset_name": "World Development Indicators (population & demographic subset)",
        "publisher": "The World Bank",
        "source_url": f"{API}/country/all/indicator/{{code}}?format=json&date={args.start}:{args.end}",
        "landing_page": "https://datacatalog.worldbank.org/search/dataset/0037712",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "release_version": lu,
        "indicator_last_updated": last_updated,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "year_range": [args.start, args.end],
        "reference_date_convention": "Annual values; WDI total population is a midyear (1 July) estimate.",
        "value_kind": "estimate",
        "uncertainty": "Not quantified by the source (WDI publishes point estimates without intervals).",
        "geographic_coverage": "World Bank economies plus regional/income aggregates (is_aggregate=true).",
        "methodology_notes": (
            "Total population counts all residents regardless of legal status or citizenship, as midyear "
            "estimates derived mainly from the UN World Population Prospects, national statistical offices "
            "and Eurostat. Values between censuses are modelled estimates, not live counts."
        ),
        "indicators": {k: {"metric": m, "unit": u} for k, (m, u) in INDICATORS.items()},
        "files": {},
    }
    for name in ("countries.json", "indicators.csv"):
        manifest["files"][name] = {"sha256": _sha256(out / name), "bytes": (out / name).stat().st_size}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} observations for {len(countries)} economies to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
