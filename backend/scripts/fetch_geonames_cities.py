"""Download a dated snapshot of GeoNames city populations for the city search.

Source: GeoNames geographical database (https://www.geonames.org), licensed CC BY 4.0.
`cities5000` lists every populated place with more than 5,000 inhabitants. The snapshot is
written to data/cities/<snapshot_id>/ as a trimmed cities.csv plus a manifest that records the
source URLs, retrieval time, row count and SHA-256 checksum. The API loads the newest snapshot.

Run with: python scripts/fetch_geonames_cities.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

BASE = "https://download.geonames.org/export/dump"
CITIES = f"{BASE}/cities5000.zip"
ADMIN1 = f"{BASE}/admin1CodesASCII.txt"
COLUMNS = ["geonameid", "name", "asciiname", "country_iso2", "admin1", "population", "modified"]


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - fixed https host
        return resp.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "cities"))
    args = parser.parse_args()

    print("Fetching admin1 names and cities5000 ...")
    admin1 = dict(line.split("\t")[:2] for line in _get(ADMIN1).decode("utf-8").splitlines() if line)
    with zipfile.ZipFile(io.BytesIO(_get(CITIES))) as zf:
        raw = zf.read("cities5000.txt").decode("utf-8")

    rows = []
    for f in csv.reader(io.StringIO(raw), delimiter="\t", quoting=csv.QUOTE_NONE):
        if int(f[14] or 0) <= 0:
            continue
        ascii_name = "" if f[2] == f[1] else f[2]  # stored only when it differs (e.g. Sao Paulo)
        rows.append([f[0], f[1], ascii_name, f[8], admin1.get(f"{f[8]}.{f[10]}", ""), f[14], f[18]])
    rows.sort(key=lambda r: -int(r[5]))

    retrieved = datetime.now(UTC)
    snapshot_id = f"geonames-{retrieved:%Y-%m-%d}"
    out = Path(args.out) / snapshot_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "cities.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    manifest = {
        "snapshot_id": snapshot_id,
        "dataset_name": "GeoNames cities5000 (populated places > 5,000 inhabitants)",
        "publisher": "GeoNames",
        "source_url": CITIES,
        "landing_page": "https://www.geonames.org",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "retrieved_at": retrieved.isoformat(timespec="seconds"),
        "row_count": len(rows),
        "value_kind": "estimate",
        "reference_date_convention": "Not specified by the source: each figure is the latest value GeoNames holds "
                                     "for the place (often a census or official estimate); `modified` is the date the "
                                     "record was last edited, not the population reference date.",
        "checksum_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} cities to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
